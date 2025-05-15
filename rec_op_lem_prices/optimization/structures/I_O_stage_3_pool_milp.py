INPUTS_S3_POOL = {
	'delta_t': 1.0,
	'horizon': 3.0,
	'l_extra': 10,
	'l_grid': [0.01, 0.01, 0.01],
	'l_lem': [0.11, 0.11, 0.11],
	'l_market_buy': [1, 1, 1],
	'l_market_sell': [-1, -1, -1],
	'l_flex': [0, 0.2, 0],
	't_flex': [1.0],
	't_no_flex': [0.0, 2.0],
	'rho_tot': [1, 1, 1],
	'meters': {
		'Meter#1': {
			'btm_storage': None,
			'c_ind': 0.352,
			'c_ind2': 0.264,
			'e_c': [0.7, 0.9, 0.6],
			'e_g': [0.0, 0.0, 0.0],
			'e_cmet2': [0.7, 0.9, 0.6],
			'l_buy': [0.16, 0.16, 0.16],
			'l_sell': [0.06, 0.06, 0.06],
			'max_p': 6.9
		},
		'Meter#2': {
			'btm_storage': {
				'Storage#1': {
					'degradation_cost': 0.00,
					'e_bn': 13.5,
					'eff_bc': 1.0,
					'eff_bd': 1.0,
					'init_e': 6.75,
					'p_max': 5.0,
					'soc_max': 95,
					'soc_min': 15}
			},
			'c_ind': -0.37949999999999995,
			'c_ind2': -0.48999999999999994,
			'e_c': [0.6, 0.6, 0.5],
			'e_g': [1.3, 1.2, 0.8],
			'e_cmet2': [-4.825, -0.9, -0.6],
			'l_buy': [0.16, 0.16, 0.16],
			'l_sell': [0.06, 0.06, 0.06],
			'max_p': 10.35
		}
	},
	'third_stage': True,  # these inputs are used for testing the second stage of the two-stage approach
	'strict_pos_coeffs': True,
	'total_share_coeffs': False
}

OUTPUTS_S3_POOL = {
	'c_ind3pool': {'Meter#1': 0.212, 'Meter#2': -1.002},
	'c_ind3pool_without_deg': {'Meter#1': 0.212, 'Meter#2': -1.002},
	'c_ind3pool_without_deg_and_p_extra': {'Meter#1': 0.212, 'Meter#2': -1.002},
	'c_ind3pool_without_p_extra': {'Meter#1': 0.212, 'Meter#2': -1.002},
	'deg_cost3pool': {'Meter#1': 0, 'Meter#2': 0},
	'delta_alc': {'Meter#1': [0.0, 0.0, 0.0],	'Meter#2': [0.0, 0.0, 0.0]},
	'delta_bc': {'Meter#1': {}, 'Meter#2': {'Storage#1': [0.0, 1.0, 0.0]}},
	'delta_cmet': {'Meter#1': [0.0, 0.0, 0.0], 'Meter#2': [0.0, 0.0, 0.0]},
	'delta_coeff': {'Meter#1': [0.0, 1.0, 1.0], 'Meter#2': [0.0, 1.0, 0.0]},
	'delta_slc': {'Meter#1': [0.0, 0.0, 1.0], 'Meter#2': [1.0, 0.0, 0.0]},
	'delta_sup': {'Meter#1': [0.0, 1.0, 1.0], 'Meter#2': [0.0, 1.0, 0.0]},
	'dual_prices': [0.06, 0.16, 0.06],
	'e_alc': {'Meter#1': [0.7, 0.0, 0.6], 'Meter#2': [0.0, 0.0, 0.0]},
	'e_bat': {'Meter#1': {}, 'Meter#2': {'Storage#1': [2.025, 7.025, 4.925]}},
	'e_bc': {'Meter#1': {}, 'Meter#2': {'Storage#1': [0.0, 5.0, 0.0]}},
	'e_bd': {'Meter#1': {}, 'Meter#2': {'Storage#1': [4.725, 0.0, 2.1]}},
	'e_cmet': {'Meter#1': [0.7, 0.9, 0.6], 'Meter#2': [-5.425, 5.6, -1.6]},
	'e_flex': {'Meter#1': [0, 0.0, 0], 'Meter#2': [0, 6.5, 0]},
	'e_gg': {'Meter#1': [0.0, 0.0, 0.0], 'Meter#2': [1.3, 0.0, 0.0]},
	'e_curt': {'Meter#1': [0.0, 0.0, 0.0], 'Meter#2': [0.0, 1.2, 0.8]},
	'e_consumed': {'Meter#1': [0.7, 0.9, 0.6], 'Meter#2': [0.0, 5.6, 0.0]},
	'e_pur_pool': {'Meter#1': [0.7, 0.0, 0.6], 'Meter#2': [0.0, 0.0, 0.0]},
	'e_sale_pool': {'Meter#1': [0.0, 0.0, 0.0], 'Meter#2': [0.7, 0.0, 0.6]},
	'e_slc_pool': {'Meter#1': [0.7, 0.0, 0.6], 'Meter#2': [0.0, 0.0, 0.0]},
	'e_sup_market': {'Meter#1': [0.0, 0.0, 0.0], 'Meter#2': [0.0, 0.0, 0.0]},
	'e_sup_retail': {'Meter#1': [0.0, 0.9, 0.0], 'Meter#2': [0.0, 5.6, 0.0]},
	'e_sur_market': {'Meter#1': [0.0, 0.0, 0.0], 'Meter#2': [0.0, 0.0, 0.0]},
	'e_sur_retail': {'Meter#1': [0.0, 0.0, 0.0], 'Meter#2': [4.725, 0.0, 1.0]},
	'milp_status': 'Optimal',
	'obj_value': -0.5905,
	'p_extra': {'Meter#1': [0.0, 0.0, 0.0], 'Meter#2': [0.0, 0.0, 0.0]},
	'p_extra_cost3pool': {'Meter#1': 0.0, 'Meter#2': 0.0},
	'soc_bat': {'Meter#1': {}, 'Meter#2': {'Storage#1': [15.0, 52.037037, 36.481481]}}
}