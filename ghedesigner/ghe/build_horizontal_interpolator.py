import multiprocessing
import os
import pickle
import time

import numpy as np
from scipy import interpolate

from ghedesigner.ghe.horizontal_pipe_heat_exchange import ParallelPipeSystem


# --- Mock Classes ---
class MockPipe:
    def __init__(self, r_out, k):
        self.r_out = r_out
        self.k = k


class MockSoil:
    def __init__(self, k, rhocp):
        self.k = k
        self.rhoCp = rhocp


# --- Worker Function ---
def worker_task(args):
    d, b, beta, r = args

    # Physics Setup (Standard Test Soil)
    pipe = MockPipe(r_out=r, k=0.4)
    soil = MockSoil(k=1.5, rhocp=2.3e6)  # k doesn't matter for dimensionless calc
    system = ParallelPipeSystem(x_coord=b, y_coord=d, pipe=pipe, soil=soil)

    # Time Grid
    years = 100
    t_min_hours = 0.01
    tau_seconds = np.logspace(np.log10(t_min_hours * 3600), np.log10(years * 365 * 24 * 3600), 80)
    final_tau_seconds = np.insert(tau_seconds, 0, 0.0)

    # Calculate EVEN Case
    q_even_raw = np.array([system.heat_transfer(t, 1.0, beta) for t in tau_seconds])

    # Boundary at t=0
    q_start_raw = 1.0 / beta
    final_q_even = np.insert(q_even_raw, 0, q_start_raw)

    interp_even = interpolate.interp1d(final_tau_seconds, final_q_even, kind="cubic", fill_value="extrapolate")

    # Calculate ODD Case
    q_odd_raw = np.array([system.heat_transfer(t, -1.0, beta) for t in tau_seconds])

    final_q_odd = np.insert(q_odd_raw, 0, q_start_raw)

    interp_odd = interpolate.interp1d(final_tau_seconds, final_q_odd, kind="cubic", fill_value="extrapolate")

    return (d, b, beta, r), interp_even, interp_odd


# --- Main Builder ---
def main():
    print("--- Building Corrected Library (Tuned Grid, No Norm) ---")
    t_start = time.perf_counter()

    # Grid Definition
    depths = np.array([0.5, 1.0, 2.0, 3.0, 5.0])
    spacings = np.array([0.3, 0.5, 0.7, 1.0, 1.5, 2.0])

    betas = np.array([1.0, 3.0, 5.0])

    radii = np.array([0.005, 0.01, 0.015, 0.026, 0.040, 0.06, 0.08, 0.10, 0.15, 0.20, 0.25])

    all_jobs = []
    for d in depths:
        for b in spacings:
            for beta in betas:
                for r in radii:
                    all_jobs.append((d, b, beta, r))

    total_jobs = len(all_jobs)
    print(f"Generating {total_jobs} curves...")

    print(f"Generating {len(all_jobs)} curves...")

    # Use all but two cores
    num_cores = max(1, os.cpu_count() - 2)

    table = {}
    with multiprocessing.Pool(processes=num_cores) as pool:
        for i, result in enumerate(pool.imap_unordered(worker_task, all_jobs), 1):
            key, i_e, i_o = result
            table[key] = (i_e, i_o)

            # Update progress display
            if i % 5 == 0 or i == total_jobs:
                elapsed_time = time.perf_counter() - t_start
                if i > 0:
                    avg_time_per_job = elapsed_time / i
                    remaining_jobs = total_jobs - i
                    eta_seconds = remaining_jobs * avg_time_per_job

                    # Formatting strings
                    eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
                    elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))

                    print(
                        f"Progress: {i}/{total_jobs} | Elapsed: {elapsed_str} | Remaining: ~{eta_str}",
                        end="\r",
                        flush=True,
                    )

    data = {
        "axes": {"depths": depths, "spacings": spacings, "betas": betas, "radii": radii},
        "table": table,
    }

    with open("horizontal_interpolator.pkl", "wb") as f:
        pickle.dump(data, f)

    print(f"Done. Saved to 'horizontal_interpolator.pkl' in {time.perf_counter() - t_start:.2f}s")


if __name__ == "__main__":
    main()
