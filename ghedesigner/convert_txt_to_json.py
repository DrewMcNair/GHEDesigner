import json
import csv

def convert_txt_to_v3_json(txt_filepath, json_filepath):
    # Initialize the base JSON structure
    out_dict = {
        "version": 3,
        "simulation_control": {},
        "fluid": {"fluid_name": "WATER", "concentration_percent": 0, "temperature": 20},
        "network_parameters": {
            "design_pressure_loss_per_meter": 0.0,
            "flow_factor": 1.0,
            "pump_efficiency": {
                "heat_pump": 1.0,
                "ghe": 1.0,
                "central_loop": 1.0
            },
            "total_loop_length": 0.0
        },
        "network": {"nodes": {}, "pipes": {}},
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

            if keyword == 'simulation_info':
                out_dict["simulation_control"]["simulation_method"] = row[1].strip()
                out_dict["simulation_control"]["simulation_years"] = int(row[2].strip())

            elif keyword == 'zone':
                # Zone, name, ISHX_ID, id, inlet_nodeID, oulet_nodeID, HPmodel, loads_file, COP_htg, COP_clg
                zone_id = row[3].strip()
                out_dict["building"][zone_id] = {
                    "inlet_node": row[4].strip(),
                    "outlet_node": row[5].strip() if row[5].strip() != "None" else None,
                    "heating_load": {
                        "file_path": row[7].strip(),
                        "heat_pump_name": row[6].strip()
                    },
                    "cooling_load": {
                        "file_path": row[7].strip(),
                        "heat_pump_name": row[6].strip()
                    }
                }

            elif keyword == 'ghe':
                # GHE, id, inlet_nodeID, outlet_nodeID, n_rows, n_cols, row_spacing, col_spacing, height, m_flow
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
                # node, id, type, x, y, z
                node_id = row[1].strip()
                out_dict["network"]["nodes"][node_id] = {
                    "type": row[2].strip(),
                    "x": float(row[3]),
                    "y": float(row[4]),
                    "z": float(row[5])
                }
                
            elif keyword == 'pipe':
                pipe_id = row[1].strip()
                out_dict["network"]["pipes"][pipe_id] = {
                    "inlet_node": row[3].strip(),
                    "outlet_node": row[4].strip(),
                    "length": float(row[5])
                }

            # --- NEW BLOCKS FOR HEAT PUMP & NETWORK PARAMS ---
            
            elif keyword == 'hpmodel':
                # HPmodel, name, id, a_htg, b_htg, c_htg, a_clg, b_clg, c_clg, c1_htg, c2_htg, c3_htg, c1_clg, c2_clg, c3_clg, m_single_hp, delta_P_HP
                hp_id = row[2].strip()
                out_dict["heat_pump"][hp_id] = {
                    "cooling_performance": {
                        "a": float(row[6]), "b": float(row[7]), "c": float(row[8]),
                        "c1": float(row[12]), "c2": float(row[13]), "c3": float(row[14]),
                        "design_cap": 0.0  # Defaulting to 0 since it wasn't explicitly in the txt
                    },
                    "heating_performance": {
                        "a": float(row[3]), "b": float(row[4]), "c": float(row[5]),
                        "c1": float(row[9]), "c2": float(row[10]), "c3": float(row[11]),
                        "design_cap": 0.0  # Defaulting to 0
                    },
                    "design_flow_rate": float(row[15]),
                    "design_pressure_loss": float(row[16]),
                    "pump_efficiency": 0.5 # Placeholder, will be overridden by network params if needed
                }

            elif keyword == 'pressure_drop':
                # pressure_drop, CL_P/m, delta_P_ref_ISHX
                out_dict["network_parameters"]["design_pressure_loss_per_meter"] = float(row[1])

            elif keyword == 'beta':
                # beta, beta_CL_flow, beta_ISHX_HP_flow, ...
                out_dict["network_parameters"]["flow_factor"] = float(row[1])

            elif keyword == 'efficiency':
                # efficiency, HP_cp_efficiency, ISHX_cp_efficiency, GHE_cp_efficiency, CL_efficiency
                out_dict["network_parameters"]["pump_efficiency"] = {
                    "heat_pump": float(row[1]),
                    "ghe": float(row[3]),
                    "central_loop": float(row[4])
                }
            
            elif keyword == 'length':
                # length, 690
                out_dict["network_parameters"]["total_loop_length"] = float(row[1])

    with open(json_filepath, 'w') as f:
        json.dump(out_dict, f, indent=2)
    print(f"Successfully converted {txt_filepath} to {json_filepath}!")

# Run the function on your file
# Make sure to replace the txt filename with exactly what it's called on your local machine
convert_txt_to_v3_json("ghedesigner/real_system_test.txt", "demos/real_system_test.json")