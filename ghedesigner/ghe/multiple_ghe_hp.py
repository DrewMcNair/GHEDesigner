# import pandas as pd
#
# # Reading the Heat Pump Loads file
# file_path_hp_loads = "C:\\Users\\nbast\\Desktop\\HeatPumpLoads\\Multiple_GHE-HP_test_data_DULUTH.csv"
#
# df1 = pd.read_csv(file_path_hp_loads, header=[0, 1, 2])
# df1.columns = pd.MultiIndex.from_tuples([(int(l1), int(l2), l3) for l1, l2, l3 in df1.columns])
#
#
# """
# def hp_constants():
#     # Heat Pump 1
#     r1_hp1 = df2.loc[:, (1, 1, "v")] * df1.loc[:, (1, 1, "HPHtgLd_W")] - df2.loc[:, (1, 1, "b")] * df1.loc[:, (1, 1, "HPClgLd_W")].to_numpy()
#     r2_hp1 = df2.loc[:, (1, 1, "u")] * df1.loc[:, (1, 1, "HPHtgLd_W")] - df2.loc[:, (1, 1, "a")] * df1.loc[:, (1, 1, "HPClgLd_W")].to_numpy()
#
#     # Heat Pump 2
#     r1_hp2 = df2.loc[:, (1, 2, "v")] * df1.loc[:, (1, 2, "HPHtgLd_W")] - df2.loc[:, (1, 2, "b")] * df1.loc[:, (1, 2, "HPClgLd_W")].to_numpy()
#     r2_hp2 = df2.loc[:, (1, 2, "u")] * df1.loc[:, (1, 2, "HPHtgLd_W")] - df2.loc[:, (1, 2, "a")] * df1.loc[:, (1, 2,  "HPClgLd_W")].to_numpy()
#
#     # Heat Pump 3
#     r1_hp3 = df2.loc[:, (1, 3, "v")] * df1.loc[:, (1, 3, "HPHtgLd_W")] - df2.loc[:, (1, 3, "b")] * df1.loc[:, (1, 3, "HPClgLd_W")].to_numpy()
#     r2_hp3 = df2.loc[:, (1, 3, "u")] * df1.loc[:, (1, 3, "HPHtgLd_W")] - df2.loc[:, (1, 3, "a")] * df1.loc[:, (1, 3, "HPClgLd_W")].to_numpy()
#
#     # Heat Pump 4
#     r1_hp4 = df2.loc[:, (1, 4, "v")] * df1.loc[:, (1, 4, "HPHtgLd_W")] - df2.loc[:, (1, 4, "b")] * df1.loc[:, (1, 4,"HPClgLd_W")].to_numpy()
#     r2_hp4 = df2.loc[:, (1, 4, "u")] * df1.loc[:, (1, 4, "HPHtgLd_W")] - df2.loc[:, (1, 4, "a")] * df1.loc[:, (1, 4,"HPClgLd_W")].to_numpy()
#
#     # Heat Pump 5
#     r1_hp5 = df2.loc[:, (1, 5, "v")] * df1.loc[:, (1, 5, "HPHtgLd_W")] - df2.loc[:, (1, 5, "b")] * df1.loc[:, (1, 5, "HPClgLd_W")].to_numpy()
#     r2_hp5 = df2.loc[:, (1, 5, "u")] * df1.loc[:, (1, 5, "HPHtgLd_W")] - df2.loc[:, (1, 5, "a")] * df1.loc[:, (1, 5, "HPClgLd_W")].to_numpy()
#
#     # Heat Pump 6
#     r1_hp6 = df2.loc[:, (1, 6, "v")] * df1.loc[:, (1, 6, "HPHtgLd_W")] - df2.loc[:, (1, 6, "b")] * df1.loc[:, (1, 6,"HPClgLd_W")].to_numpy()
#     r2_hp6 = df2.loc[:, (1, 6, "u")] * df1.loc[:, (1, 6, "HPHtgLd_W")] - df2.loc[:, (1, 6, "a")] * df1.loc[:, (1, 6,"HPClgLd_W")].to_numpy()
#
#     return r1_hp1, r2_hp1, r1_hp2, r2_hp2, r1_hp3, r2_hp3, r1_hp4, r2_hp4, r1_hp5, r2_hp5, r1_hp6, r2_hp6
# """
#
# # I calculate run_time_fraction and all mass flow rates in within the simulation at ground_heat_exchangers.py
# # It is not imported form here, this code is only for reference but these outputs are not exported to
# # ground_heat_exchangers.py.
#
# """
# def run_time_fraction(c1_hp1_htg, c2_hp1_htg, c1_hp1_clg, c2_hp1_clg, c1_hp2_htg, c2_hp2_htg, c1_hp2_clg, c2_hp2_clg,
#                       c1_hp3_htg, c2_hp3_htg, c1_hp3_clg, c2_hp3_clg, t_eft):
#
#     q_net_htg_hp1 = df1.loc[:, 1, 1, "HPHtgLd_W"] - df1.loc[:, (1, 1, "HPClgLd_W")]
#     q_net_htg_hp2 = df1.loc[:, 1, 2, "HPHtgLd_W"] - df1.loc[:, (1, 2, "HPClgLd_W")]
#     q_net_htg_hp3 = df1.loc[:, 1, 3, "HPHtgLd_W"] - df1.loc[:, (1, 3, "HPClgLd_W")]
#
#     hp1_capacity = (c1_hp1_htg * t_eft + c2_hp1_htg) if q_net_htg_hp1 > 0 else (c1_hp1_clg * t_eft + c2_hp1_clg)
#     hp2_capacity = (c1_hp2_htg * t_eft + c2_hp2_htg) if q_net_htg_hp2 > 0 else (c1_hp2_clg * t_eft + c2_hp2_clg)
#     hp3_capacity = (c1_hp3_htg * t_eft + c2_hp3_htg) if q_net_htg_hp3 > 0 else (c1_hp3_clg * t_eft + c2_hp3_clg)
#
#     here t_eft is changing every hour within the simulation,so I need to code it such that it uses that t_eft
#      of previous step to calculate capacity
#      I need to think about hp capacity is whether for heating and cooling because the models for htg and cooling are
#      not same.
#
#     run_time_factor_hp1 = abs(q_net_htg_hp1)/hp1_capacity
#     run_time_factor_hp2 = abs(q_net_htg_hp2)/hp2_capacity
#     run_time_factor_hp3 = abs(q_net_htg_hp3)/hp3_capacity
#
#     return run_time_factor_hp1, run_time_factor_hp2, run_time_factor_hp3
# """
# """
# def mass_flow_rate_hp(m_hp1_design, m_hp2_design, m_hp3_design, rtf_hp1, rtf_hp2, rtf_hp3):
#     m_hp1 = m_hp1_design * rtf_hp1
#     m_hp2 = m_hp2_design * rtf_hp2
#     m_hp3 = m_hp3_design * rtf_hp3
#
#     return m_hp1, m_hp2, m_hp3
#
#
# def mass_flow_loop(m_hp1, m_hp2, m_hp3, beta):
#     return beta * (m_hp1 + m_hp2 + m_hp3)
#
#
# def mass_flow_ghe(m_loop, nbh_ghe1, nbh_ghe2, nbh_total):
#     m_ghe1 = m_loop * nbh_ghe1/nbh_total
#     m_ghe2 = m_loop * nbh_ghe2/nbh_total
#
#     return m_ghe1, m_ghe2
#
#
# """
# def extract_time_array():
#     """
#     Extracts the time values from the specified location in the dataframe
#     and converts them into a NumPy array.
#
#     Returns:
#     A NumPy array containing the extracted time values.
#     """
#     time_array = df1.iloc[:, 0].to_numpy()
#     return time_array
#
#
# def time_array_size():
#     size = len(extract_time_array())
#     return size
#
# result = time_array_size()
# print(result)
# """
# def main():
#     # Defining variables
#     c1_hp1_htg = c1_hp2_htg = c1_hp3_htg = 106.26
#     c2_hp1_htg = c2_hp2_htg = c2_hp3_htg = 4196.1
#     c1_hp1_clg = c1_hp2_clg = c1_hp3_clg = -50.47
#     c2_hp1_clg = c2_hp2_clg = c2_hp3_clg = 6954.2
#     beta = 3  # assumption
#     m_hp1_design = 0.284  # kg/s 4.5 GPM
#     m_hp2_design = 0.473  # kg/s 7.5 GPM
#     m_hp3_design = 0.662  # kg/s  10.5 GPM
#
#     rtf_hp1, rtf_hp2, rtf_hp3 = run_time_fraction(c1_hp1_htg, c2_hp1_htg, c1_hp1_clg, c2_hp1_clg, c1_hp2_htg,
#                                                   c2_hp2_htg, c1_hp2_clg, c2_hp2_clg, c1_hp3_htg, c2_hp3_htg,
#                                                   c1_hp3_clg, c2_hp3_clg, t_eft)
#
#     m_hp1, m_hp2, m_hp3 = mass_flow_rate_hp(m_hp1_design, m_hp2_design, m_hp3_design, rtf_hp1, rtf_hp2, rtf_hp3)
#     m_loop = mass_flow_loop(m_hp1, m_hp2, m_hp3, beta)
#     m_ghe1, m_ghe2 = mass_flow_ghe(m_loop, nbh_ghe1, nbh_ghe2, nbh_total)
#
#     delta_t_hp = 5
#     beta = 3
#     c_p = 4200
#
#     time_hours = extract_time_array()
#     size_array = time_array_size()
#     print(time_hours)
#     print(size_array)
#
#
#
# if __name__ == "__main__":
#     main()
# """
