import time
from pathlib import Path

from ghedesigner.ghe.manager import _run_manager_from_cli_worker

start_time = time.time()


def main():
    input_filename = Path("find_design_rectangle_single_u_tube_HOUSTON.json")
    output_directory = Path("results")
    _run_manager_from_cli_worker(input_filename, output_directory)


if __name__ == "__main__":
    main()

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Total time taken: {elapsed_time:.4f} seconds")
