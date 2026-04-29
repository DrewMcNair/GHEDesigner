import json
import csv

def convert_txt_to_v3_json(txt_filepath, json_filepath):
    # Initialize the base JSON structure
    out_dict = {
        "version": 3,
        "simulation_control": {},
        "fluid": {"fluid_name": "WATER", "concentration_percent": 0, "temperature": 20},
        "network_parameters": {
            "pipe_configuration": "1-pipe", # Default, will be overwritten if found in txt
            "design_pressure_loss_per_meter": 0.0,
            "flow_factor": 1.0,
            "pump_efficiency": {
                "heat_pump": 1.0,
                "ghe": 1.0,
                "central_loop": 1.0
            },
            "total_loop_length": 0.0
        },
        "network": {"nodes": {}, "pipelines": {}},
        "heat_pump": {},
        "building": {},
        "ground_heat_exchanger": {}
    }

    # Default properties required by GHEDesigner that aren't in the txt file
    default_ghe_props = {
        "flow_type": "BOREHOLE",
        "grout": {"conductivity": 1.0, "rho_cp": 3901000},
        "soil": {"conductivity": 2.0, "rho_cp": 2343493, "undisturbed_temp": 15.0},
        "pipe": {"inner_diameter": 0.03404, "outer_diameter": 0.04216, "shank_spacing": 0.01856, 
                 "roughness": 1e-06, "conductivity": 0.4, "rho_cp": 1542000, "arrangement": "SINGLEUTUBE"},
        "borehole": {"buried_depth": 2.0, "diameter": 0.14}
    }

    with open(txt_filepath, 'r') as f:
        reader = csv.reader(f, skipinitialspace=True)
        for row in reader:
            if not row or row[0].strip().startswith('#'):
                continue
            
            keyword = row[0].strip().lower()

            if keyword == 'configuration':
                # e.g., configuration, '1-pipe' -> stripping the single quotes
                out_dict["network_parameters"]["pipe_configuration"] = row[1].strip().strip("'\"")

            elif keyword == 'simulation_info':
                out_dict["simulation_control"]["simulation_method"] = row[1].strip()
                out_dict["simulation_control"]["simulation_years"] = int(row[2].strip())

            elif keyword == 'zone':
                zone_id = row[3].strip()
                loads_path = row[7].strip()
                
                # Check what columns are actually in this specific file
                try:
                    with open(loads_path, 'r') as f_check:
                        header = f_check.readline().strip().split(',')
                except:
                    header = [] # Fallback if file isn't found yet

                bldg_entry = {
                    "inlet_node": row[4].strip(),
                    "outlet_node": row[5].strip() if row[5].strip() != "None" else None,
                    "heating_load": {
                        "file_path": loads_path,
                        "heat_pump_name": row[6].strip(),
                        "column_name": "HPHtgLd_W"
                    }
                }

                # Only add cooling if the column exists in the CSV
                if "HPClgLd_W" in header:
                    bldg_entry["cooling_load"] = {
                        "file_path": loads_path,
                        "heat_pump_name": row[6].strip(),
                        "column_name": "HPClgLd_W"
                    }
                
                out_dict["building"][zone_id] = bldg_entry

            elif keyword == 'ghe':
                ghe_id = row[1].strip()
                ghe_obj = dict(default_ghe_props)
                ghe_obj["inlet_node"] = row[2].strip()
                ghe_obj["outlet_node"] = row[3].strip() if row[3].strip() != "None" else None
                ghe_obj["flow_rate"] = float(row[9].strip())
                ghe_obj["pre_designed"] = {
                    "arrangement": "RECTANGLE",
                    "boreholes_in_x_dimension": int(row[4]),
                    "boreholes_in_y_dimension": int(row[5]),
                    "spacing_in_x_dimension": float(row[6]),
                    "spacing_in_y_dimension": float(row[7]),
                    "H": float(row[8])
                }
                out_dict["ground_heat_exchanger"][ghe_id] = ghe_obj

            elif keyword == 'node':
                node_id = row[1].strip()
                out_dict["network"]["nodes"][node_id] = {
                    "type": row[2].strip(),
                    "x": float(row[3]),
                    "y": float(row[4]),
                    "z": float(row[5])
                }
                
            elif keyword == 'pipeline':
                pipe_id = row[1].strip()
                out_dict["network"]["pipelines"][pipe_id] = {
                    "inlet_node": row[2].strip(),
                    "outlet_node": row[3].strip(),
                    "length": float(row[4])
                }

            elif keyword == 'hpmodel':
                hp_id = row[2].strip()
                out_dict["heat_pump"][hp_id] = {
                    "cooling_performance": {
                        "a": float(row[6]), "b": float(row[7]), "c": float(row[8]),
                        "c1": float(row[12]), "c2": float(row[13]), "c3": float(row[14]),
                        "design_cap": 0.0  
                    },
                    "heating_performance": {
                        "a": float(row[3]), "b": float(row[4]), "c": float(row[5]),
                        "c1": float(row[9]), "c2": float(row[10]), "c3": float(row[11]),
                        "design_cap": 0.0  
                    },
                    "design_flow_rate": float(row[15]),
                    "design_pressure_loss": float(row[16])
                }

            elif keyword == 'pressure_drop':
                out_dict["network_parameters"]["design_pressure_loss_per_meter"] = float(row[1])

            elif keyword == 'beta':
                out_dict["network_parameters"]["flow_factor"] = float(row[1])

            elif keyword == 'efficiency':
                out_dict["network_parameters"]["pump_efficiency"] = {
                    "heat_pump": float(row[1]),
                    "ghe": float(row[3]),
                    "central_loop": float(row[4])
                }
            
            elif keyword == 'length':
                out_dict["network_parameters"]["total_loop_length"] = float(row[1])

    with open(json_filepath, 'w') as f:
        json.dump(out_dict, f, indent=2)
    print(f"Successfully converted {txt_filepath} to {json_filepath}!")

if __name__ == "__main__":
    # Example usage:
    convert_txt_to_v3_json("ghedesigner/real_system_test.txt", "demos/real_system_test.json")