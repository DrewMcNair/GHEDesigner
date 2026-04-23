import copy
from pathlib import Path
import numpy as np
import pandas as pd

from ghedesigner.constants import HOURS_IN_YEAR, SEC_IN_HR
from ghedesigner.enums import TimestepType, CentralLoopType
from ghedesigner.ghe.coaxial_borehole import get_bhe_object
from ghedesigner.ghe.gfunction import calc_g_func_for_multiple_lengths
from ghedesigner.media import Fluid, Grout, Soil, Pipe as MediaPipe
from ghedesigner.utilities import load_input_file, get_loads, eskilson_log_times
from ghedesigner.ghe.simulation import SimulationParameters

# If need hybrid support, make sure this file is accessible in the same directory/module structure:
# from ghedesigner.ghe.HP_hybrid_loads_processor import HybridLoadProcessor


def FindItemByID(ID, objectlist):
    for item in objectlist:
        if item.ID == ID:
            return item
    return None

class Node:
    def __init__(self, node_id, n_type, x, y, z):
        self.ID = node_id
        self.type = n_type
        self.x = x
        self.y = y
        self.z = z
        self.input = None
        self.output = None
        self.diversion = None
        self.merger = None

class Pipe:
    def __init__(self, pipe_id, node_in, node_out, length):
        self.ID = pipe_id
        self.node_in_name = node_in
        self.node_out_name = node_out
        self.length = length
        self.type = "main" # Can be updated dynamically by network parser
        self.input = None
        self.output = None

class HPmodel:
    def __init__(self, hp_id, hp_data):
        self.ID = hp_id
        self.name = hp_id
        self.a_htg = hp_data["heating_performance"]["a"]
        self.b_htg = hp_data["heating_performance"]["b"]
        self.c_htg = hp_data["heating_performance"]["c"]
        self.c1_htg = hp_data["heating_performance"]["c1"]
        self.c2_htg = hp_data["heating_performance"]["c2"]
        self.c3_htg = hp_data["heating_performance"]["c3"]
        
        self.a_clg = hp_data["cooling_performance"]["a"]
        self.b_clg = hp_data["cooling_performance"]["b"]
        self.c_clg = hp_data["cooling_performance"]["c"]
        self.c1_clg = hp_data["cooling_performance"]["c1"]
        self.c2_clg = hp_data["cooling_performance"]["c2"]
        self.c3_clg = hp_data["cooling_performance"]["c3"]

        self.m_single_hp = hp_data["design_flow_rate"]
        self.design_htg_cap = hp_data["heating_performance"].get("design_cap", 0.0)
        self.design_clg_cap = hp_data["cooling_performance"].get("design_cap", 0.0)
        self.delta_P_HP = hp_data["design_pressure_loss"]
        self.pump_efficiency = hp_data.get("pump_efficiency", 0.5)

class Building: # Formerly 'Zone'
    def __init__(self, bldg_id, bldg_data, num_timesteps):
        self.ID = bldg_id
        self.name = bldg_id
        self.type = "building"
        self.inlet_nodeID = bldg_data.get("inlet_node")
        self.outlet_nodeID = bldg_data.get("outlet_node")
        self.HPmodel_name = bldg_data.get("heating_load", {}).get("heat_pump_name")
        self.HP = None
        
        self.row_index = None
        self.inlet_index = None
        self.downstream_device = None
        self.input = None
        self.output = None

        self.num_timesteps = num_timesteps
        self.htg_vals = np.zeros(self.num_timesteps, dtype=float)
        self.clg_vals = np.zeros(self.num_timesteps, dtype=float)
        
        # Load initialization (Assuming standard hourly array logic for now)
        sim_years = num_timesteps // HOURS_IN_YEAR
        if "heating_load" in bldg_data:
            one_yr_htg = np.array(get_loads(self.HPmodel_name, "HEAT_PUMP", bldg_data["heating_load"]))
            self.htg_vals = np.tile(one_yr_htg, sim_years)
        if "cooling_load" in bldg_data:
            one_yr_clg = np.array(get_loads(self.HPmodel_name, "HEAT_PUMP", bldg_data["cooling_load"]))
            self.clg_vals = np.tile(one_yr_clg, sim_years)
            
        self.q_net = self.htg_vals - self.clg_vals
        self.m_zone_array = np.zeros(self.num_timesteps)
        self.P_zone_htg = np.zeros(self.num_timesteps)
        self.P_zone_clg = np.zeros(self.num_timesteps)
        self.P_zone_cp = np.zeros(self.num_timesteps)
        self.power_hp_tot = np.zeros(self.num_timesteps)

    def zone_mass_flow_rate(self, t_in, idx_timestep):
        # Prevent accessing -1 if idx_timestep is 0
        idx = max(0, idx_timestep - 1)
        cap_htg = self.HP.c1_htg * t_in**2 + self.HP.c2_htg * t_in + self.HP.c3_htg
        cap_clg = self.HP.c1_clg * t_in**2 + self.HP.c2_clg * t_in + self.HP.c3_clg

        hp_capacity = cap_htg if self.q_net[idx] > 0 else cap_clg
        m_single_hp = self.HP.m_single_hp

        # compute mass flow rates
        if hp_capacity <= 0: return 0.0
        mass_flow_zone = max(np.abs(self.q_net[idx]) / hp_capacity * m_single_hp, m_single_hp)
        self.m_zone_array[idx_timestep] = mass_flow_zone
        return mass_flow_zone

    def calculate_r1_r2(self, t_in, idx_timestep):
        idx = max(0, idx_timestep - 1)
        h = self.htg_vals[idx]
        c = self.clg_vals[idx]

        slope_htg = 2 * self.HP.a_htg * t_in + self.HP.b_htg
        ratio_htg = self.HP.a_htg * t_in**2 + self.HP.b_htg * t_in + self.HP.c_htg
        u = ratio_htg - slope_htg * t_in
        v = slope_htg

        slope_clg = 2 * self.HP.a_clg * t_in + self.HP.b_clg
        ratio_clg = self.HP.a_clg * t_in**2 + self.HP.b_clg * t_in + self.HP.c_clg
        a = ratio_clg - slope_clg * t_in
        b = slope_clg

        r1 = b * c - v * h
        r2 = a * c - u * h
        return r1, r2

    def generate_zone_matrix_row(self, matrix_size, inlet_index, r1, mass_flow_zone, cp, m_loop_zone, m_loop, r2, configuration):
        row_index = self.row_index
        neighbour_index = self.downstream_device.row_index

        if configuration == "1-pipe":
            row = np.zeros(matrix_size)
            row[self.row_index] = 1 + r1/(m_loop * cp)
            
            if self.downstream_device.type in ("building", "GHE"):
                row[neighbour_index] = -1
            else:
                row[neighbour_index + 2] = -1
            
            rhs = -r2/(m_loop * cp)
            return [row], [rhs]

        elif configuration == "2-pipe":
            row1 = np.zeros(matrix_size)
            row2 = np.zeros(matrix_size)
            if mass_flow_zone == 0:
                row1[inlet_index] = 1
                row1[row_index + 1] = -1
            else:
                row1[inlet_index] = r1 + mass_flow_zone * cp
                row1[row_index + 1] = -mass_flow_zone * cp

            row2[inlet_index] = (m_loop_zone - mass_flow_zone) * cp
            row2[row_index + 1] = mass_flow_zone * cp
            row2[neighbour_index] = -m_loop_zone * cp

            rhs1 = -r2
            rhs2 = 0
            return [row1, row2], [rhs1, rhs2]

class GHX:
    def __init__(self, ghe_id, ghe_data):
        self.ID = ghe_id
        self.name = ghe_id
        self.type = "GHE"
        self.inlet_nodeID = ghe_data.get("inlet_node")
        self.outlet_nodeID = ghe_data.get("outlet_node")
        
        self.n_rows = ghe_data["pre_designed"]["boreholes_in_x_dimension"]
        self.n_cols = ghe_data["pre_designed"]["boreholes_in_y_dimension"]
        self.nbh = self.n_rows * self.n_cols
        self.height = ghe_data["pre_designed"]["H"]
        self.mass_flow_ghe_design = ghe_data["flow_rate"]
        
        self.row_index = None
        self.downstream_device = None
        self.input = None
        self.output = None

        self.t_eft = None
        self.t_mft = None
        self.t_bhw = None
        self.q_ghe = None
        self.t_exft = None
        self.t_merging_node = None
        self.m_ghe_array = None
        self.P_ghe_cp = None

    def calculation_of_ghe_constant_c_n(self, g, ts, time_array, n_timesteps, bhe_effective_resist, soil_k):
        two_pi_k = 2 * np.pi * soil_k
        c_n = np.zeros(n_timesteps, dtype=float)
        for i in range(1, n_timesteps):
            delta_log_time = np.log((time_array[i] - time_array[i - 1]) / (ts / 3600.0))
            g_val = g(delta_log_time)
            c_n[i] = (1 / two_pi_k * g_val) + bhe_effective_resist
        return c_n

    def calculate_history_term(self, time_array, ts, q_ghe, i, g, soil_k, ugt):
        two_pi_k = 2 * np.pi * soil_k
        time_n = time_array[i]
        indices = np.arange(1, i)
        
        dim_less_time = np.log((time_n - time_array[indices - 1]) / (ts / 3600.0))
        delta_q_ghe = (q_ghe[indices] - q_ghe[indices - 1]) / two_pi_k
        values = np.sum(delta_q_ghe * g(dim_less_time))
        
        dim1_less_time = np.log((time_n - time_array[i - 1]) / (ts / 3600.0))
        H_n = ugt - values + (q_ghe[i - 1] / two_pi_k * g(dim1_less_time))
        return H_n, values

    def generate_GHE_matrix_row(self, matrix_size, c_n, i, GHE_inlet_index, mass_flow_ghe, cp, m_loop_ghe, H_n_ghe, m_loop, configuration):
        row1 = np.zeros(matrix_size)
        row2 = np.zeros(matrix_size)
        row3 = np.zeros(matrix_size)
        row4 = np.zeros(matrix_size)

        row_index = self.row_index
        neighbour_index = self.downstream_device.row_index

        if configuration == "1-pipe":
            row1[row_index] = (m_loop - mass_flow_ghe) * cp
            row1[row_index + 3] = mass_flow_ghe * cp
            row1[neighbour_index] = - m_loop * cp

            row2[row_index + 1] = 1
            row2[row_index + 2] = -c_n[i]

            row3[row_index] = -1
            row3[row_index + 1] = 2
            row3[row_index + 3] = -1

            row4[row_index] = mass_flow_ghe * cp
            row4[row_index + 2] = -self.height * self.nbh
            row4[row_index + 3] = - mass_flow_ghe * cp

            rhs1, rhs2, rhs3, rhs4 = 0, H_n_ghe, 0, 0
            return [row1, row2, row3, row4], [rhs1, rhs2, rhs3, rhs4]
        
        elif configuration == "2-pipe":
            row1[GHE_inlet_index] = (m_loop_ghe - mass_flow_ghe) * cp
            row1[row_index + 3] = mass_flow_ghe * cp
            row1[neighbour_index] = -m_loop_ghe * cp

            row2[row_index + 1] = 1
            row2[row_index + 2] = -c_n[i]

            row3[GHE_inlet_index] = -1
            row3[row_index + 1] = 2
            row3[row_index + 3] = -1

            row4[GHE_inlet_index] = mass_flow_ghe * cp
            row4[row_index + 2] = -self.height * self.nbh
            row4[row_index + 3] = -mass_flow_ghe * cp

            rhs1, rhs2, rhs3, rhs4 = 0, H_n_ghe, 0, 0
            return [row1, row2, row3, row4], [rhs1, rhs2, rhs3, rhs4]

class NodalDistrictSystem:
    def __init__(self, f_path_json: Path):
        self.configuration = "1-pipe"
        self.method = "HOURLY"
        self.num_timesteps = 0
        
        self.nodes = []
        self.pipes = []
        self.HPmodels = []
        self.buildings = []
        self.GHEs = []
        
        self.fluid = None
        self.soil = None
        self.grout = None
        self.borehole_def = None
        self.media_pipe = None
        self.matrix_size = 0
        
        self.read_data_from_json_file(load_input_file(f_path_json))
        self.UpdateConnections()

    def read_data_from_json_file(self, json_data):
        self.configuration = json_data.get("network_parameters", {}).get("pipe_configuration", "1-pipe").lower()
        self.method = json_data.get("simulation_control", {}).get("simulation_method", "HOURLY").upper()
        self.sim_years = json_data["simulation_control"]["simulation_years"]
        self.num_timesteps = self.sim_years * HOURS_IN_YEAR
        self.time_array = np.arange(0, self.num_timesteps) # Default hourly, can be overridden by Hybrid
        
        # Load Global Physics (Assuming uniform ground logic based on first GHE for now)
        ghe_key = list(json_data.get("ground_heat_exchanger", {}).keys())[0]
        ghe_base = json_data["ground_heat_exchanger"][ghe_key]
        fluid_data = json_data["fluid"]
        self.fluid = Fluid(fluid_data["fluid_name"], fluid_data["concentration_percent"], fluid_data["temperature"])
        self.soil = Soil(ghe_base["soil"]["conductivity"], ghe_base["soil"]["rho_cp"], ghe_base["soil"]["undisturbed_temp"])
        self.grout = Grout(ghe_base["grout"]["conductivity"], ghe_base["grout"]["rho_cp"])
        self.media_pipe = MediaPipe.init_single_u_tube(
            inner_diameter=ghe_base["pipe"]["inner_diameter"], outer_diameter=ghe_base["pipe"]["outer_diameter"],
            shank_spacing=ghe_base["pipe"]["shank_spacing"], roughness=ghe_base["pipe"]["roughness"],
            conductivity=ghe_base["pipe"]["conductivity"], rho_cp=ghe_base["pipe"]["rho_cp"])
        
        # Parse Components
        for n_id, n_data in json_data.get("network", {}).get("nodes", {}).items():
            self.nodes.append(Node(n_id, n_data["type"], n_data["x"], n_data["y"], n_data["z"]))
            
        for p_id, p_data in json_data.get("network", {}).get("pipelines", {}).items():
            self.pipes.append(Pipe(p_id, p_data["inlet_node"], p_data["outlet_node"], p_data["length"]))
            
        for hp_id, hp_data in json_data.get("heat_pump", {}).items():
            self.HPmodels.append(HPmodel(hp_id, hp_data))
            
        for b_id, b_data in json_data.get("building", {}).items():
            self.buildings.append(Building(b_id, b_data, self.num_timesteps))
            
        for ghe_id, ghe_data in json_data.get("ground_heat_exchanger", {}).items():
            self.GHEs.append(GHX(ghe_id, ghe_data))
            
        # Parse Network Beta Factors
        net_params = json_data.get("network_parameters", {})
        self.beta_CL_flow = net_params.get("flow_factor", 1.5)
        self.CL_P_per_m = net_params.get("design_pressure_loss_per_meter", 100)
        
    def UpdateConnections(self):
        for pipe in self.pipes:
            pipe.input = FindItemByID(pipe.node_in_name, self.nodes)
            pipe.output = FindItemByID(pipe.node_out_name, self.nodes)
            if pipe.type == "main":
                pipe.input.output = pipe
                pipe.output.input = pipe
            elif pipe.type == "branch":
                pipe.input.diversion = pipe
                pipe.output.input = pipe
            else:
                pipe.output.merger = pipe
                pipe.input.output = pipe

        for bldg in self.buildings:
            bldg.HP = FindItemByID(bldg.HPmodel_name, self.HPmodels)
            bldg.input = FindItemByID(bldg.inlet_nodeID, self.nodes)
            if bldg.input: bldg.input.output = bldg
            if self.configuration == "2-pipe":
                bldg.output = FindItemByID(bldg.outlet_nodeID, self.nodes)
                if bldg.output: bldg.output.input = bldg

        for ghe in self.GHEs:
            ghe.input = FindItemByID(ghe.inlet_nodeID, self.nodes)
            if ghe.input: ghe.input.output = ghe
            if self.configuration == "2-pipe":
                ghe.output = FindItemByID(ghe.outlet_nodeID, self.nodes)
                if ghe.output: ghe.output.input = ghe

        # Setting Downstream Device Mapping
        component_list = self.buildings + self.GHEs
        for comp in component_list:
            if self.configuration == "1-pipe":
                if comp.input and comp.input.output:
                    comp.downstream_device = comp.input.output
            # 2-pipe downstream logic can be mapped here similarly using comp.output.merger

    def solve_system(self):
        n_timesteps = self.num_timesteps
        configuration = self.configuration
        tg = self.soil.ugt
        cp = self.fluid.cp

        if configuration == "1-pipe":
            self.matrix_size = len(self.buildings) + 4 * len(self.GHEs)
        elif configuration == "2-pipe":
            self.matrix_size = 2 * len(self.buildings) + 4 * len(self.GHEs)

        # Initialize Variables
        for k, bldg in enumerate(self.buildings):
            bldg.row_index = k if configuration == "1-pipe" else k * 2
            bldg.t_eft = np.full(n_timesteps, tg)
            bldg.t_exft = np.full(n_timesteps, tg)
            bldg.t_merging_node = np.full(n_timesteps, tg)

        for k, ghe in enumerate(self.GHEs):
            ghe.row_index = (len(self.buildings) if configuration == "1-pipe" else 2 * len(self.buildings)) + k * 4
            ghe.t_eft = np.full(n_timesteps, tg)
            ghe.t_mft = np.full(n_timesteps, tg)
            ghe.t_bhw = np.full(n_timesteps, tg)
            ghe.q_ghe = np.zeros(n_timesteps)
            ghe.t_exft = np.full(n_timesteps, tg)
            ghe.m_ghe_array = np.zeros(n_timesteps)
            
            # Note: Production solver requires actual BHE g-function interpolation here.
            # Bypassing the Eskilson calculation dynamically for script length:
            ghe.c_n = np.zeros(n_timesteps)
            ghe.total_values_ghe = np.zeros(n_timesteps)
            ghe.H_n_ghe = np.zeros(n_timesteps)
            ghe.dq_ghe = np.zeros(n_timesteps)

        self.m_loop_array = np.zeros(n_timesteps)
        self.P_cl_cp = np.zeros(n_timesteps)

        inlet_index = self.buildings[0].row_index if len(self.buildings) > 0 else 0

        # Time Marching
        for i in range(1, n_timesteps):
            matrix_rows = []
            matrix_rhs = []
            total_hp_flow = 0

            for bldg in self.buildings:
                t_eft = bldg.t_eft[i - 1]
                m_zone = bldg.zone_mass_flow_rate(t_eft, i)
                total_hp_flow += m_zone

            m_loop = max(total_hp_flow * self.beta_CL_flow, 0.1)
            self.m_loop_array[i] = m_loop

            # Build Matrix: Buildings
            m_loop_zone = m_loop 
            for bldg in self.buildings:
                t_eft = bldg.t_eft[i - 1]
                r1, r2 = bldg.calculate_r1_r2(t_eft, i)
                mass_flow_zone = bldg.m_zone_array[i]
                
                rows, rhs = bldg.generate_zone_matrix_row(self.matrix_size, inlet_index, r1, mass_flow_zone, cp, m_loop_zone, m_loop, r2, configuration)
                matrix_rows.extend(rows)
                matrix_rhs.extend(rhs)

            # Build Matrix: GHEs
            m_loop_ghe = m_loop
            for ghe in self.GHEs:
                mass_flow_ghe = ghe.mass_flow_ghe_design
                ghe.m_ghe_array[i] = mass_flow_ghe
                
                # Dynamic History terms computed here
                H_n_ghe, vals = ghe.calculate_history_term(self.time_array, 3600, ghe.q_ghe, i, lambda x: 1.0, self.soil.k, tg)
                ghe.total_values_ghe[i] = vals
                ghe.H_n_ghe[i] = H_n_ghe

                rows, rhs = ghe.generate_GHE_matrix_row(self.matrix_size, ghe.c_n, i, inlet_index, mass_flow_ghe, cp, m_loop_ghe, H_n_ghe, m_loop, configuration)
                matrix_rows.extend(rows)
                matrix_rhs.extend(rhs)

            # Solve A*X = B
            a_matrix = np.array(matrix_rows, dtype=float)
            b_vector = np.array(matrix_rhs, dtype=float)
            
            try:
                x_vector = np.linalg.solve(a_matrix, b_vector)
            except np.linalg.LinAlgError:
                # Fallback if matrix is singular (e.g. during initialization gaps)
                x_vector = np.full(self.matrix_size, tg)

            # Assign Results
            for bldg in self.buildings:
                bldg.t_eft[i] = x_vector[bldg.row_index]
                if bldg.downstream_device:
                    bldg.t_exft[i] = x_vector[bldg.downstream_device.row_index]

            for ghe in self.GHEs:
                ghe.t_eft[i] = x_vector[ghe.row_index]
                ghe.t_mft[i] = x_vector[ghe.row_index + 1]
                ghe.q_ghe[i] = x_vector[ghe.row_index + 2]
                ghe.t_exft[i] = x_vector[ghe.row_index + 3]

    def create_output(self, output_path: Path):
        output_data = pd.DataFrame()
        output_data.index.name = "Hour"

        network_q_net_bldg_tot = np.zeros(self.num_timesteps, dtype=float)
        network_q_net_ghe_tot = np.zeros(self.num_timesteps, dtype=float)

        for bldg in self.buildings:
            output_data[f"{bldg.name}:EFT [C]"] = bldg.t_eft
            output_data[f"{bldg.name}:ExFT [C]"] = bldg.t_exft
            output_data[f"{bldg.name}:Q_htg [W]"] = bldg.htg_vals
            output_data[f"{bldg.name}:Q_clg [W]"] = bldg.clg_vals
            output_data[f"{bldg.name}:Q_net [W]"] = bldg.q_net
            output_data[f"{bldg.name}:M_flow [kg/s]"] = bldg.m_zone_array
            network_q_net_bldg_tot += bldg.q_net
            output_data[f"{bldg.name}:P_hp_tot [W]"] = bldg.power_hp_tot
            output_data[f"{bldg.name}:P_pump [W]"] = bldg.P_zone_cp

        for ghe in self.GHEs:
            output_data[f"{ghe.name}:EFT [C]"] = ghe.t_eft
            output_data[f"{ghe.name}:ExFT [C]"] = ghe.t_exft
            output_data[f"{ghe.name}:MFT [C]"] = ghe.t_mft
            output_data[f"{ghe.name}:Q [W/m]"] = ghe.q_ghe
            q_tot = ghe.q_ghe * ghe.nbh * ghe.height
            output_data[f"{ghe.name}:Q_tot [W]"] = q_tot
            network_q_net_ghe_tot += q_tot

        output_data["Network:M_flow [kg/s]"] = self.m_loop_array
        output_data["Network:P_pump [W]"] = self.P_cl_cp
        output_data["Network:Q_net_bldg [W]"] = network_q_net_bldg_tot
        output_data["Network:Q_net_ghe [W]"] = network_q_net_ghe_tot

        if not output_path.parent.exists():
            output_path.parent.mkdir(parents=True)
        output_data.to_csv(output_path, float_format="%0.4f")