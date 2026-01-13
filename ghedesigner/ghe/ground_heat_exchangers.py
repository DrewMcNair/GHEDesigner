from math import ceil

import numpy as np
import pandas as pd
from pygfunction.boreholes import Borehole
from scipy.interpolate import interp1d
from scipy.optimize import fsolve

from ghedesigner import VERSION
from ghedesigner.constants import TWO_PI
from ghedesigner.enums import BHPipeType, TimestepType
from ghedesigner.ghe.coaxial_borehole import get_bhe_object
from ghedesigner.ghe.gfunction import GFunction, calc_g_func_for_multiple_lengths
from ghedesigner.ghe.ground_loads import HybridLoad
from ghedesigner.ghe.simulation import SimulationParameters
from ghedesigner.media import Grout, Pipe, Soil
from ghedesigner.utilities import solve_root

# Reading data for heat pumps, loads, HP_coefficients and model.

f1 = open("Simulation_file_constant_COP_HOUSTON.txt")
data = f1.readlines()
f1.close()

for line in data:
    cells = [c.strip() for c in line.strip().split(',')]
    keyword = cells[0].lower()

    if keyword == "quadratic":
        a_htg = float(cells[1])
        b_htg = float(cells[2])
        c_htg = float(cells[3])
        a_clg = float(cells[4])
        b_clg = float(cells[5])
        c_clg = float(cells[6])

    if keyword == "linear":
        a_htg_lin = float(cells[1])
        b_htg_lin = float(cells[2])
        a_clg_lin = float(cells[3])
        b_clg_lin = float(cells[4])

    if keyword == "cop":
        COP_htg = float(cells[1])
        COP_clg = float(cells[2])

    if keyword == "hp_model":
        HP_model = str(cells[1])

    if keyword == "solution_method":
        solution_method = str(cells[1])

    if keyword == "loads":
        df = pd.read_csv(cells[1])
        time_array = df['Hours'].values
        n_timesteps = len(time_array)


class BaseGHE:
    def __init__(
        self,
        v_flow_system: float,
        b_spacing: float,
        bhe_type: BHPipeType,
        fluid,
        borehole: Borehole,
        pipe: Pipe,
        grout: Grout,
        soil: Soil,
        g_function: GFunction,
        sim_params: SimulationParameters,
        hourly_extraction_ground_loads: list,
        field_type="N/A",
        field_specifier="N/A",
    ) -> None:
        self.fieldType = field_type
        self.fieldSpecifier = field_specifier
        self.V_flow_system = v_flow_system
        self.B_spacing = b_spacing
        self.nbh = len(g_function.bore_locations)
        self.V_flow_borehole = self.V_flow_system / self.nbh
        m_flow_borehole = self.V_flow_borehole / 1000.0 * fluid.rho
        self.m_flow_borehole = m_flow_borehole

        # Borehole Heat Exchanger
        self.bhe_type = bhe_type
        self.bhe = get_bhe_object(bhe_type, m_flow_borehole, fluid, borehole, pipe, grout, soil)
        # Equivalent borehole Heat Exchanger
        self.bhe_eq = self.bhe.to_single()

        # Radial numerical short time step
        self.bhe_eq.calc_sts_g_functions()

        # gFunction object
        self.gFunction = g_function

        # Additional simulation parameters
        self.sim_params = sim_params
        # Hourly ground extraction loads
        # Building cooling is negative, building heating is positive
        self.hourly_extraction_ground_loads = hourly_extraction_ground_loads
        self.times = np.empty((0,), dtype=np.float64)
        self.loading = None

        self.n_timesteps = n_timesteps
        self.time_array = time_array
        self.df = df

    def as_dict(self) -> dict:
        output = {
            "title": f"GHEDesigner GHE Output - Version {VERSION}",
            "number_of_boreholes": len(self.gFunction.bore_locations),
            "borehole_depth": {"value": self.bhe.b.H, "units": "m"},
            "borehole_spacing": {"value": self.B_spacing, "units": "m"},
            "borehole_heat_exchanger": self.bhe.as_dict(),
            "equivalent_borehole_heat_exchanger": self.bhe_eq.as_dict(),
            "simulation_parameters": self.sim_params.as_dict(),
        }
        return output

    @staticmethod
    def combine_sts_lts(log_time_lts: list, g_lts: list, log_time_sts: list, g_sts: list) -> interp1d:
        # make sure the short time step doesn't overlap with the long time step
        max_log_time_sts = max(log_time_sts)
        min_log_time_lts = min(log_time_lts)

        if max_log_time_sts < min_log_time_lts:
            log_time = log_time_sts + log_time_lts
            g = g_sts + g_lts
        else:
            # find where to stop in sts
            i = 0
            value = log_time_sts[i]
            while value <= min_log_time_lts:
                i += 1
                value = log_time_sts[i]
            log_time = log_time_sts[0:i] + log_time_lts
            g = g_sts[0:i] + g_lts
        g = interp1d(log_time, g)

        return g

    def grab_g_function(self, b_over_h):
        # interpolate for the Long time step g-function
        g_function, rb_value, _, _ = self.gFunction.g_function_interpolation(b_over_h)
        # correct the long time step for borehole radius
        g_function_corrected = self.gFunction.borehole_radius_correction(g_function, rb_value, self.bhe.b.r_b)
        # Don't Update the HybridLoad (its dependent on the STS) because
        # it doesn't change the results much, and it slows things down a lot
        # combine the short and long time step g-function
        g = self.combine_sts_lts(
            self.gFunction.log_time,
            g_function_corrected,
            self.bhe_eq.lntts.tolist(),
            self.bhe_eq.g.tolist(),
        )

        g_bhw = self.combine_sts_lts(
            self.gFunction.log_time,
            g_function_corrected,
            self.bhe_eq.lntts.tolist(),
            self.bhe_eq.g_bhw.tolist(),
        )
        return g, g_bhw

    def cost(self, max_eft, min_eft):
        delta_t_max = max_eft - self.sim_params.max_EFT_allowable
        delta_t_min = self.sim_params.min_EFT_allowable - min_eft
        t_excess = max(delta_t_max, delta_t_min)
        return t_excess

    def calculate_r1_r2(self, t_eft, i, HP_model):
        """
        Calculate r1 and r2 for this zone based on entering fluid temperature and HP coefficients.
        """

        # Extract loads
        h_loads = self.df["HPHtgLd_W"].iloc[i] if "HPHtgLd_W" in self.df.columns else 0.0
        c_loads = self.df["HPClgLd_W"].iloc[i] if "HPClgLd_W" in self.df.columns else 0.0

        if HP_model == "quadratic":
            pass

        elif HP_model == "linearized":
            # Heating calculations
            slope_htg = 2 * a_htg * t_eft + b_htg
            ratio_htg = a_htg * t_eft**2 + b_htg * t_eft + c_htg
            u = ratio_htg - slope_htg * t_eft
            v = slope_htg

            # Cooling calculations
            slope_clg = 2 * a_clg * t_eft + b_clg
            ratio_clg = a_clg * t_eft**2 + b_clg * t_eft + c_clg
            a = ratio_clg - slope_clg * t_eft
            b = slope_clg

            # Final r1 and r2
            r1 = b * c_loads - v * h_loads
            r2 = a * c_loads - u * h_loads

        elif HP_model == "linear":
            r1 = b_clg_lin * c_loads - b_htg_lin * h_loads
            r2 = a_clg_lin * c_loads - a_htg_lin * h_loads

        elif HP_model == "constant_COP":
            R_htg = 1 - 1 / COP_htg
            R_clg = 1 + 1 / COP_clg

            r1 = 0
            r2 = R_clg * c_loads - R_htg * h_loads

        else:
            raise ValueError("Only four Heat_pump_models are available")

        return r1, r2

    def calculation_of_ghe_constant_c_n(self, g, ts, time_array, n_timesteps, bhe_effective_resist):
        """
        Calculate C_n values for three GHEs based on their g-functions.

        Cn = 1 / (2 * pi * K_s) * g((tn - tn-1) / t_s) + R_b
        """

        two_pi_k = 2 * np.pi * self.bhe.soil.k
        c_n = np.zeros(n_timesteps, dtype=float)

        for i in range(1, n_timesteps):
            delta_log_time = np.log((time_array[i] - time_array[i - 1]) / (ts / 3600.0))
            g_val = g(delta_log_time)
            c_n[i] = (1 / two_pi_k * g_val) + bhe_effective_resist

        return c_n

    def compute_history_term(self, i, time_array, ts, two_pi_k, g, tg, H_n_ghe, total_values_ghe, q_ghe):
        """
        Computes the history term H_n for this GHX at time index `i`.
        Updates self.total_values_ghe and self.H_n_ghe in place.
        """
        if i == 0:
            H_n_ghe[i] = tg
            total_values_ghe[i] = 0
            return

        time_n = time_array[i]

        # Compute dimensionless time for all indices from 1 to i-1
        indices = np.arange(1, i)
        dim_less_time = np.log((time_n - time_array[indices - 1]) / (ts / 3600.0))

        # Compute contributions from all previous steps
        delta_q_ghe = (q_ghe[indices] - q_ghe[indices - 1]) / two_pi_k
        values = np.sum(delta_q_ghe * g(dim_less_time))

        total_values_ghe[i] = values

        # Contribution from the last time step only
        dim1_less_time = np.log((time_n - time_array[i - 1]) / (ts / 3600.0))

        H_n_ghe[i] = tg + total_values_ghe[i] - (q_ghe[i - 1] / two_pi_k * g(dim1_less_time))
        return H_n_ghe[i]

    def _simulate_detailed(self):
        """
        Solves for X_values matrix using the provided parameters and equations. The matrix solves four variables:
        MFT, EFT, ExFT and q extracted.

         Args:
            self: An instance of the class containing necessary attributes.
            g: Interpolation function for the g-function.
            c_n: Array of c_n values.

        Returns:
               X_values: List of X values at each time step.
        """

        ts = self.bhe_eq.t_s  # (-)
        tg = self.bhe.soil.ugt  # (Celsius)
        two_pi_k = TWO_PI * self.bhe.soil.k  # (W/m.K)
        m_dot = self.bhe.m_flow_borehole  # (kg/s)
        h = self.bhe.b.H  # (meters)
        cp = self.bhe.fluid.cp  # (J/kg.s)
        c = m_dot * cp
        b = self.B_spacing
        b_over_h = b / self.bhe.b.H
        bhe_effective_resist = self.bhe.calc_effective_borehole_resistance()
        g, _ = self.grab_g_function(b_over_h)
        c_n = self.calculation_of_ghe_constant_c_n(g, ts, self.time_array, self.n_timesteps, bhe_effective_resist)
        mft = np.zeros(self.n_timesteps)
        hp_eft = np.full(self.n_timesteps, tg)
        hp_exft = np.full(self.n_timesteps, tg)
        q_ghe = np.zeros(self.n_timesteps)
        tb = np.zeros(self.n_timesteps)
        delta_tb = np.zeros(self.n_timesteps)
        total_values = np.zeros(self.n_timesteps)
        H_n_ghe = np.zeros(self.n_timesteps)
        r1 = np.zeros(self.n_timesteps)
        r2 = np.zeros(self.n_timesteps)
        total_values_ghe = np.zeros(self.n_timesteps)

        for i in range(1, self.n_timesteps):
            H_n_ghe[i] = self.compute_history_term(
                i, self.time_array, ts, two_pi_k, g, tg, H_n_ghe, total_values_ghe, q_ghe
            )

            # Solving matrix for nth timestep
            if solution_method == "matrix_solver":
                r1[i], r2[i] = self.calculate_r1_r2(hp_eft[i - 1], i, HP_model)
                A = np.array(
                    [[2, -1, -1, 0], [1, 0, 0, -c_n[i]], [0, -r1[i], 0, h * self.nbh], [0, c, -c, h * self.nbh]]
                )
                B = np.array([0, H_n_ghe[i], r2[i], 0])
                X = np.linalg.solve(A, B)

                mft[i] = X[0]
                hp_eft[i] = X[1]
                hp_exft[i] = X[2]
                q_ghe[i] = X[3]
                tb[i] = hp_eft[i] + (q_ghe[i] * bhe_effective_resist)
                delta_tb[i] = tg - tb[i]

                tb = hp_eft + (q_ghe * bhe_effective_resist)
                delta_tb = tg - tb

            # Solving non-linear equation for quadratic model
            elif solution_method == "non_linear_solver":
                # Extract loads
                h_loads = self.df["HPHtgLd_W"].iloc[i] if "HPHtgLd_W" in self.df.columns else 0.0
                c_loads = self.df["HPClgLd_W"].iloc[i] if "HPClgLd_W" in self.df.columns else 0.0

                def equations(vars):
                    mft_i, hp_eft_i, hp_exft_i, q_ghe_i = vars
                    eq1 = 2 * mft_i - hp_eft_i - hp_exft_i
                    eq2 = mft_i - c_n[i] * q_ghe_i - H_n_ghe[i]
                    eq3 = c * hp_eft_i - c * hp_exft_i + h * self.nbh * q_ghe_i
                    eq4 = (
                        ((a_clg * hp_eft_i**2 + b_clg * hp_eft_i + c_clg) * c_loads)
                        - ((a_htg * hp_eft_i**2 + b_htg * hp_eft_i + c_htg) * h_loads)
                        - (q_ghe_i * h * self.nbh)
                    )
                    return np.array([eq1, eq2, eq3, eq4])

                initial_guess = np.array([tg, tg, tg, -20])

                solution = fsolve(equations, initial_guess)

                mft[i], hp_eft[i], hp_exft[i], q_ghe[i] = solution

                tb = hp_eft + (q_ghe * bhe_effective_resist)
                delta_tb = tg - tb

            else:
                raise ValueError("Only two methods available")

        return mft, hp_eft, hp_exft, q_ghe, delta_tb

    def compute_g_functions(self):
        # Compute g-functions for a bracketed solution, based on min and max
        # height
        min_height = self.sim_params.min_height
        max_height = self.sim_params.max_height
        avg_height = (min_height + max_height) / 2.0
        h_values = [min_height, avg_height, max_height]

        coordinates = self.gFunction.bore_locations
        log_time = self.gFunction.log_time

        g_function = calc_g_func_for_multiple_lengths(
            self.B_spacing,
            h_values,
            self.bhe.b.r_b,
            self.bhe.b.D,
            self.bhe.m_flow_borehole,
            self.bhe_type,
            log_time,
            coordinates,
            self.bhe.fluid,
            self.bhe.pipe,
            self.bhe.grout,
            self.bhe.soil,
        )

        self.gFunction = g_function


class GHE(BaseGHE):
    def __init__(
        self,
        v_flow_system: float,
        b_spacing: float,
        bhe_type: BHPipeType,
        fluid,
        borehole: Borehole,
        pipe: Pipe,
        grout: Grout,
        soil: Soil,
        g_function: GFunction,
        sim_params: SimulationParameters,
        hourly_extraction_ground_loads: list,
        field_type="N/A",
        field_specifier="N/A",
        load_years=None,
    ) -> None:
        BaseGHE.__init__(
            self,
            v_flow_system,
            b_spacing,
            bhe_type,
            fluid,
            borehole,
            pipe,
            grout,
            soil,
            g_function,
            sim_params,
            hourly_extraction_ground_loads,
            field_type=field_type,
            field_specifier=field_specifier,
        )

        # Split the extraction loads into heating and cooling for input to
        # the HybridLoad object
        if load_years is None:
            load_years = [2019]

        hybrid_load = HybridLoad(
            self.hourly_extraction_ground_loads, self.bhe_eq, self.bhe_eq, sim_params, years=load_years
        )

        # hybrid load object
        self.hybrid_load = hybrid_load

    def simulate(self, method: TimestepType):
        b = self.B_spacing
        b_over_h = b / self.bhe.b.H

        # Solve for equivalent single U-tube
        self.bhe_eq = self.bhe.to_single()
        # Update short time step object with equivalent single u-tube
        self.bhe_eq.calc_sts_g_functions()
        # Combine the short and long-term g-functions. The long term g-function
        # is interpolated for specific B/H and rb/H values.
        g, _ = self.grab_g_function(b_over_h)

        if method == TimestepType.HYBRID:
            q_dot = self.hybrid_load.load[2:] * 1000.0  # convert to Watts
            time_values = self.hybrid_load.hour[2:]  # convert to seconds
            self.times = time_values
            self.loading = q_dot
            mft, hp_eft, hp_exft, q_ghe, d_tb = self._simulate_detailed()

        elif method == TimestepType.HOURLY:
            n_months = self.sim_params.end_month - self.sim_params.start_month + 1
            n_hours = int(n_months / 12.0 * 8760)
            q_dot = self.hourly_extraction_ground_loads
            # How many times does q need to be repeated?
            n_years = ceil(n_hours / 8760)
            if len(q_dot) // 8760 < n_years:
                q_dot = q_dot * n_years
            else:
                n_hours = len(q_dot)
            # q_dot = -1.0 * np.array(q_dot)  # Convert loads to rejection
            if len(self.times) == 0:
                self.times = np.arange(1, n_hours + 1, 1)
            t = self.times

            mft, hp_eft, hp_exft, q_ghe, d_tb = self._simulate_detailed()
            self.loading = np.hstack((0.0, q_ghe, q_ghe[-1]))

        else:
            raise ValueError("Only hybrid or hourly methods available.")

        self.mft = mft
        self.hp_eft = hp_eft
        self.hp_exft = hp_exft
        self.q_ghe = q_ghe
        self.dTb = d_tb
        print(
            self.bhe.b.H, self.nbh, b, max(hp_eft), min(hp_eft)
        )  # I want to just check these values during simulation, so I am printing it: comment by NB
        return max(hp_eft), min(hp_eft)

    def size(self, method: TimestepType) -> None:
        # Size the ground heat exchanger
        def local_objective(h):
            self.bhe.b.H = h
            max_hp_eft, min_hp_eft = self.simulate(method=method)
            t_excess = self.cost(max_hp_eft, min_hp_eft)
            return t_excess

        # Make the initial guess variable the average of the heights given
        self.bhe.b.H = (self.sim_params.max_height + self.sim_params.min_height) / 2.0
        # bhe.b.H is updated during sizing
        returned_height = solve_root(
            self.bhe.b.H,
            local_objective,
            lower=self.sim_params.min_height,
            upper=self.sim_params.max_height,
            abs_tol=1.0e-6,
            rel_tol=1.0e-6,
            max_iter=50,
        )

        self.bhe.b.H = returned_height

    def calculate(self, _hour_index: int, inlet_temp: float, _flow_rate: float) -> float:
        effectiveness = 0.5
        soil_temp = 20

        return effectiveness * (soil_temp - inlet_temp) + inlet_temp
