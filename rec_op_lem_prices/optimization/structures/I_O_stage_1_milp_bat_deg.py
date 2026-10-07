INPUTS_S1 = {
	'btm_storage': {
		'Storage#1': {
			'degradation_cost': 0.01,
			'e_bn': 1.0,
			'eff_bc': 1.0,
			'eff_bd': 1.0,
			'init_e': 0.0,
			'p_max': 1.0,
			'soc_max': 100.0,
			'soc_min': 0.0
		}
	},
	'bat_deg_data': {
			'num_pts_real': 100,
			'num_seg_approx': 7,
			'curve': {'a1': -6.6315 * (10 ** 5),'a2': 8.782 * (10 ** 4),'a3': -10.86,'a4': 6.681 * (10 ** 5),'a5': -0.002277},
			'capex': 2000
	},
	'delta_t': 1.0,
	'e_c': [0.0, 0.5, 0.0],
	'e_g': [0.9, 0.0, 0.0],
	'horizon': 3.0,
	'id': 'Meter#1',
	'l_buy': [1.0, 2.0, 0.0],
	'l_extra': 10,
	'l_market_buy': [2.0, 2.0, 0.0],
	'l_market_sell': [0.0, 0.0, 1.0],
	'l_sell': [0.0, 0.0, 0.0],
	'max_p': 5.0
}

OUTPUTS_S1 = {'meter_id': 'Meter#1', 'obj_value': 0.11612842603539997, 'milp_status': 'Optimal', 'e_sup_retail': [0.0, 0.0, 0.0], 'e_sur_retail': [0.0, 0.0, 0.0], 'e_sup_market': [0.0, 0.0, 0.0], 'e_sur_market': [0.0, 0.0, 0.4], 'delta_sup': [1.0, 1.0, 0.0], 'e_cmet': [0.0, 0.0, -0.4], 'p_extra': [0.0, 0.0, 0.0], 'e_bat': {'Storage#1': [0.9, 0.4, 0.0]}, 'soc_bat': {'Storage#1': [90.0, 40.0, 0.0]}, 'e_bc': {'Storage#1': [0.9, 0.0, 0.0]}, 'e_bd': {'Storage#1': [0.0, 0.5, 0.4]}, 'delta_bc': {'Storage#1': [1.0, 0.0, 0.0]}, 'cost_deg': {'Storage#1': [0.5161284260354, 0.0, 0.0]}, 'p_extra_cost': 0.0, 'c_ind': 0.11612842603539997, 'c_ind_without_deg': -0.4, 'c_ind_without_p_extra': 0.11612842603539997, 'c_ind_without_deg_and_p_extra': -0.4}
