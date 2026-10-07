INPUTS_S2_POOL_P2H_FIXED = {
    'delta_t': 1,
    'horizon': 4,
    'l_extra': 10,
    'l_grid': [0.01] * 4,
    'l_lem': [0.2] * 4,
    'l_market_buy': [1.5] * 4,
    'l_market_sell': [0.0] * 4,
    'h2_sell': [6, 6, 6, 0],
    'CHP': [0.5, 0.5, 0.5, 0.5],
    'meters': {
        'Meter#1': {
            'c_ind': 10,
            'e_c': [0, 4, 4, 10],
            'e_g': [10.05 * 2, 14.35 * 2, 14.15 * 2, 0],
            'l_buy': [0.16] * 4,
            'l_sell': [0.0] * 4,
            'max_p': 100,
            'electrolyzer': {
                # Defined such that EC produces 1 kg of H2 throughout simulation
                'Electrolyzer#1': {
                    'pn': 9.85 * 2,
                    'p_min': 0,
                    'eff': 1,
                    'link': 'H2Tank#1'
                }
            },
            'h2_tank': {
                'H2Tank#1': {
                    'capacity': 1,
                    'init_h2': 0,
                    'h2_min': 0
                }
            },
            'fuel_cell': {
                'FuelCell#1': {
                    'pn': 1,
                    'p_min': 0,
                    'eff': 1,
                    'link': 'H2Tank#1'
                }
            }
        },
        "Meter#2": {
            'c_ind': 10,
            'e_c': [0.2, 0.5, 0.8, 0.5],
            'e_g': [0, 0, 0.5, 1],
            'l_buy': [0.16] * 4,
            'l_sell': [0.0] * 4,
            'max_p': 40,
        }
    },
    'second_stage': True
}

# This test is meant to show members pooling energy into the electrolyzer to produce 1 kg of hydrogen
# Hydrogen should be attractive, but not too attractive to lead to additional imports
OUTPUTS_S2_POOL_P2H_FIXED = {
    "obj_value": -1.625,
    "milp_status": "Optimal",
    "e_sup_retail": {
        "Meter#1": [0.0, 0.0, 0.0, 8.5],
        "Meter#2": [0.0, 0.0, 0.0, 0.0]
    },
    "e_sur_retail": {
        "Meter#1": [0.2, 0.0, 0.0, 0.0],
        "Meter#2": [0.0, 0.0, 0.0, 0.0]
    },
    "e_sup_market": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "e_sur_market": {
        "Meter#1": [
            0.0,
            24.2,
            23.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "delta_sup": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            1.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            1.0
        ]
    },
    "e_pur_pool": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.5
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            0.0
        ]
    },
    "e_sale_pool": {
        "Meter#1": [
            0.2,
            0.5,
            0.3,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.5
        ]
    },
    "e_cmet": {
        "Meter#1": [
            -0.4,
            -24.7,
            -23.3,
            9.0
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            -0.5
        ]
    },
    "e_slc_pool": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.5
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            0.0
        ]
    },
    "e_consumed": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            9.0
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            0.0
        ]
    },
    "e_alc": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.5
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            0.0
        ]
    },
    "delta_slc": {
        "Meter#1": [
            1.0,
            1.0,
            1.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            1.0,
            1.0
        ]
    },
    "delta_cmet": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "delta_alc": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "p_extra": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "e_ec_total": {
        "Meter#1": {
            "Electrolyzer#1": [
                19.7,
                0.0,
                1.0,
                0.0
            ]
        }
    },
    "h2_storage": {
        "Meter#1": {
            "H2Tank#1": [
                0.5,
                0.0,
                0.025380711,
                0.0
            ]
        }
    },
    "m_chp": {
        "Meter#1": {
            "H2Tank#1": [
                0.0,
                0.5,
                0.0,
                0.0
            ]
        }
    },
    "e_fc_total": {
        "Meter#1": {
            "FuelCell#1": [
                0.0,
                0.0,
                0.0,
                1.0
            ]
        }
    },
    "m_fc": {
        "Meter#1": {
            "FuelCell#1": [
                0.0,
                0.0,
                0.0,
                0.025380711
            ]
        }
    },
    "m_h2": {
        "Meter#1": {
            "Electrolyzer#1": [
                0.5,
                0.0,
                0.025380711,
                0.0
            ]
        }
    },
    "c_ind2pool": {
        "Meter#1": 1.264,
        "Meter#2": 0.109
    },
    "deg_cost2pool": {
        "Meter#1": 0,
        "Meter#2": 0
    },
    "p_extra_cost2pool": {
        "Meter#1": 0.0,
        "Meter#2": 0.0
    },
    "c_ind2pool_without_deg": {
        "Meter#1": 1.264,
        "Meter#2": 0.109
    },
    "c_ind2pool_without_p_extra": {
        "Meter#1": 1.264,
        "Meter#2": 0.109
    },
    "c_ind2pool_without_deg_and_p_extra": {
        "Meter#1": 1.264,
        "Meter#2": 0.109
    },
    "dual_prices": [
        0.0,
        0.0,
        0.0,
        0.15
    ]
}

INPUTS_S2_POOL_P2H_VARIABLE = {
    'delta_t': 1,
    'horizon': 4,
    'l_extra': 10,
    'l_grid': [0.01] * 4,
    'l_lem': [0.2] * 4,
    'l_market_buy': [1.5] * 4,
    'l_market_sell': [0.0] * 4,
    'h2_sell': [6, 6, 6, 0],
    'CHP': [0.5, 0.5, 0.5, 0.5],
    'variable_efficiency_ec': True,
    'variable_efficiency_fc': True,
    'meters': {
        'Meter#1': {
            'c_ind': 10,
            'e_c': [0, 4, 4, 10],
            'e_g': [10.05 * 2, 14.35 * 2, 14.15 * 2, 0],
            'l_buy': [0.16] * 4,
            'l_sell': [0.0] * 4,
            'max_p': 100,
            'electrolyzer': {
                # Defined such that EC produces 1 kg of H2 throughout simulation
                'Electrolyzer#1': {
                    'pn': 9.85 * 2,
                    'p_min': 0,
                    'eff': 1,
                    'link': 'H2Tank#1',
                    'eff': [
                        (20, 66),
                        (55, 78.32),
                        (100, 68.50)
                    ]
                }
            },
            'h2_tank': {
                'H2Tank#1': {
                    'capacity': 1,
                    'init_h2': 0,
                    'h2_min': 0
                }
            },
            'fuel_cell': {
                'FuelCell#1': {
                    'pn': 1,
                    'p_min': 0,
                    'eff': 1,
                    'link': 'H2Tank#1',
                    'eff': [
                        (20, 52.12),
                        (40, 57.48),
                        (100, 56.28)
                    ]
                }
            }
        },
        "Meter#2": {
            'c_ind': 10,
            'e_c': [0.2, 0.5, 0.8, 0.5],
            'e_g': [0, 0, 0.5, 1],
            'l_buy': [0.16] * 4,
            'l_sell': [0.0] * 4,
            'max_p': 40,
        }
    },
    'second_stage': True
}

OUTPUTS_S2_POOL_P2H_VARIABLE = {
    "obj_value": -1.625,
    "milp_status": "Optimal",
    "e_sup_retail": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            8.5
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "e_sur_retail": {
        "Meter#1": [
            0.0,
            0.0,
            24.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "e_sup_market": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "e_sur_market": {
        "Meter#1": [
            0.2,
            4.5,
            0.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "delta_sup": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            1.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "e_pur_pool": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.5
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            0.0
        ]
    },
    "e_sale_pool": {
        "Meter#1": [
            0.2,
            0.5,
            0.3,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.5
        ]
    },
    "e_cmet": {
        "Meter#1": [
            -0.4,
            -5.0,
            -24.3,
            9.0
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            -0.5
        ]
    },
    "e_slc_pool": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.5
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            0.0
        ]
    },
    "e_consumed": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            9.0
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            0.0
        ]
    },
    "e_alc": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.5
        ],
        "Meter#2": [
            0.2,
            0.5,
            0.3,
            0.0
        ]
    },
    "delta_slc": {
        "Meter#1": [
            1.0,
            1.0,
            1.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            1.0,
            1.0
        ]
    },
    "delta_cmet": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "delta_alc": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "p_extra": {
        "Meter#1": [
            0.0,
            0.0,
            0.0,
            0.0
        ],
        "Meter#2": [
            0.0,
            0.0,
            0.0,
            0.0
        ]
    },
    "e_ec_total": {
        "Meter#1": {
            "Electrolyzer#1": [
                19.7,
                19.7,
                0.0,
                0.0
            ]
        }
    },
    "h2_storage": {
        "Meter#1": {
            "H2Tank#1": [
                0.34211,
                0.68422,
                0.18422,
                0.17026
            ]
        }
    },
    "m_chp": {
        "Meter#1": {
            "H2Tank#1": [
                0.0,
                0.0,
                0.5,
                0.0
            ]
        }
    },
    "e_fc_total": {
        "Meter#1": {
            "FuelCell#1": [
                0.0,
                0.0,
                0.0,
                1.0
            ]
        }
    },
    "m_fc": {
        "Meter#1": {
            "FuelCell#1": [
                0.0,
                0.0,
                0.0,
                0.01396
            ]
        }
    },
    "m_h2": {
        "Meter#1": {
            "Electrolyzer#1": [
                0.34211,
                0.34211,
                0.0,
                0.0
            ]
        }
    },
    "c_ind2pool": {
        "Meter#1": 1.264,
        "Meter#2": 0.109
    },
    "deg_cost2pool": {
        "Meter#1": 0,
        "Meter#2": 0
    },
    "p_extra_cost2pool": {
        "Meter#1": 0.0,
        "Meter#2": 0.0
    },
    "c_ind2pool_without_deg": {
        "Meter#1": 1.264,
        "Meter#2": 0.109
    },
    "c_ind2pool_without_p_extra": {
        "Meter#1": 1.264,
        "Meter#2": 0.109
    },
    "c_ind2pool_without_deg_and_p_extra": {
        "Meter#1": 1.264,
        "Meter#2": 0.109
    },
    "dual_prices": [
        0.0,
        0.0,
        0.0,
        0.15
    ]
}
