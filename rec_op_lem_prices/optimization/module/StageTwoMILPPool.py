"""
Class for implementing and running the Stage 2 MILP for an energy community.
The implementation is specific to a pool market structure.
"""
import itertools
import os
import math

from rec_op_lem_prices.configs.configs import (
    MIPGAP,
    SOLVER,
    TIMEOUT
)
from rec_op_lem_prices.optimization.helpers.milp_helpers import (
    dict_none_lists,
    dict_per_param,
    none_lists,
    round_up,
    time_intervals
)
from rec_op_lem_prices.custom_types.stage_two_milp_pool_types import (
    BackpackS2PoolDict,
    OutputsS2PoolDict
)
from loguru import logger
from pulp import (
    CPLEX_CMD,
    HiGHS_CMD,
    listSolvers,
    LpBinary,
    LpMinimize,
    LpProblem,
    LpStatus,
    lpSum,
    LpVariable,
    GUROBI_CMD,
    pulp,
    value, LpInteger
)


def piecewise_linearization(equipment_dict: dict):
    """
    Returns a list of tuples that contain the slopes and intercepts of hydrogen production.
    The values that must be in the 'eff' dict must be lists of tuples, for example [(0, 0)], [(5, 31)]
    """
    maximum_power = equipment_dict["pn"]
    eff_points = equipment_dict["eff"]

    # Separate the columns
    power_column = [p / 100 * maximum_power for p, _ in eff_points]
    eff_column = [eff / 100 for _, eff in eff_points]

    # Required for conversion to hydrogen production
    mass = [e * p / 39.4 for e, p in zip(eff_column, power_column)]

    slopes = [
        round((mass[i + 1] - mass[i]) / (power_column[i + 1] - power_column[i]), 4)
        for i in range(len(mass) - 1)
    ]

    intercepts = [
        round(mass[i] - slopes[i] * power_column[i], 4)
        for i in range(len(mass) - 1)
    ]

    slope_intercepts = list(zip(slopes, intercepts))
    return slope_intercepts, power_column

class StageTwoMILPPool:
    def __init__(self, backpack: BackpackS2PoolDict, solver=SOLVER, timeout=TIMEOUT, mipgap=MIPGAP):
        # Indices and sets
        self._horizon = backpack.get('horizon')  # operation period (hours)
        # Parameters
        self._delta_t = backpack.get('delta_t')  # interval settlement duration [h]
        self._l_buy = None  # supply energy tariff [€/kWh]
        self._l_sell = None  # feed in energy tariff [€/kWh]
        self._l_market_buy = backpack.get('l_market_buy')  # market-indexed buying tariff [€/kWh]
        self._l_market_sell = backpack.get('l_market_sell')  # market-indexed selling tariff [€/kWh]
        self._e_c = None  # Meter load profile [kWh]
        self._e_g = None  # Meter generation [kWh]
        self._p_meter_max = None  # power flow limit at the Meter [kW]
        self._c_ind = None  # objective function values of each Meters' 1st stage MILP solution
        self._l_grid = backpack.get('l_grid')  # access tariff of the local grid [€/kWh]
        self._l_lem = backpack.get('l_lem')  # price for LEM transactions [€/kWh]
        self._big_m = None  # a very big number [kWh]
        self._l_extra = backpack.get('l_extra')  # (fictitious) very high cost of violating p_meter_max

        # MILP variables
        self.milp = None  # for storing the MILP formulation
        self.solver = solver  # solver chosen for the MILP
        self.timeout = timeout  # solvers temporal limit to find optimal solution (s)
        self.mipgap = mipgap  # controls the solver's tolerance; intolerant [0 - 1] fully permissive
        self.status = None  # stores the status of the MILP's solution
        self.obj_value = None  # stores the MILP's numeric solution
        self.time_intervals = None  # for number of time intervals per horizon
        self.time_series = None  # for a range of time intervals
        self.set_meters = None  # set with Meters' ID

        self._meters_data = backpack.get('meters')  # data from Meters
        self.second_stage = backpack.get('second_stage')  # indicates if second stage (True) or single stage (False)
        self.strict_pos_coeffs = backpack.get('strict_pos_coeffs')  # no negative coefficients if True
        self.total_share_coeffs = backpack.get('total_share_coeffs')  # share all required in the REC if True

        # BESS
        self.sets_btm_storage = {}  # stores the Meter's Btm storage assets' ids
        self._eff_bc = {}  # charging efficiency of the batteries [%]
        self._eff_bd = {}  # discharging efficiency of batteries [%]
        self._p_max = {}  # maximum input and output batteries' power [kW]
        self._e_bn = {}  # nominal capacity of the batteries'[kWh]
        self._soc_min = {}  # minimum state of charge of the batteries [%]
        self._soc_max = {}  # maximum state of charge of the batteries [%]
        self._init_e_bat = {}  # initial energy content of the batteries [kWh]
        self._deg_cost = {}  # estimated degradation cost of the batteries of n [€/kWh]

        # EV
        self.sets_btm_ev = {}  # stores the Meter's Btm EVs ids
        self._trip_ev = {}  # EV energy consumption, in kWh
        self._min_energy_storage_ev = {}  # Minimum stored energy to be guaranteed for vehicle ev at CPE n, in kWh
        self._battery_capacity_ev = {}  # The battery energy capacity of vehicle ev at CPE n, in kWh
        self._eff_bc_ev = {}  # Charging efficiency of vehicle ev at CPE n, between 0 and 1
        self._eff_bd_ev = {}  # Discharging efficiency of vehicle ev at CPE n, between 0 and 1
        self._init_e_ev = {}  # the initial energy content of the EV, in kWh
        self._pmax_c_ev = {}  # Maximum power charge of vehicle ev at CPE n, in kW
        self._pmax_d_ev = {}  # Maximum power discharge of vehicle ev at CPE n, in kW
        self._bin_ev = {}  # Whether a vehicle ev at CPE n is plugged-in or not (if plugged-in = 1 else = 0)

        # EWH
        self._ewh_paramsInput = {}
        self._ewh_dataset = {}
        self.set_ewh = {}
        self.wh_init = {}
        self.ewh_power = {}
        self.delta_t = {}
        self.ewh_start_temp = {}
        self.ewh_capacity = {}
        self.waterHeatCap = {}
        self.heatTransferCoeff = {}
        self.ewh_area = {}
        self.ambTemp = {}
        self.wh_min = {}
        self.wh_max = {}
        self.ewh_min_temp = {}
        self.ewh_max_temp = {}
        self.delta_use = {}
        self.tempSet = {}
        self.bigNumber = {}
        self.regressor_aboveSet_m_temp = {}
        self.regressor_aboveSet_m_delta = {}
        self.regressor_aboveSet_b = {}
        self.regressor_belowSet_m_temp = {}
        self.regressor_belowSet_m_delta = {}
        self.regressor_belowSet_b = {}
        # HVAC
        self._hvac = backpack.get('hvac')
        self.mu = {}  # Building insulation factor
        self.psi = {}  # HVAC temperature efficiency factor
        self.hvac_temp_min = {}  # Min room temperature constraint
        self.hvac_temp_max = {}  # Max room temperature constraint
        self.hvac_init_temp = {}  # Initial room temperature
        self.hvac_capacity = {}  # Maximum HVAC power
        self.T_out = {}  # Outside temperature
        self.set_hvac = {}  # Set of active HVAC units
        self.thermal_resist = {}
        self.thermal_cap = {}
        self.type = {}
        # HP
        self._hp = backpack.get('hp')
        self.set_hp = {}
        self.hp_type = {}
        self.hp_power_rated = {}
        self.hp_capacity_tank = {}
        self.hp_c_p = {}
        self.hp_temp_inlet = {}
        self.hp_temp_desired = {}
        self.hp_temp_out_init = {}
        self.hp_temp_indoor_init = {}
        self.hp_temp_indoor_final = {}
        self.hp_temp_indoor_min = {}
        self.hp_temp_indoor_max = {}
        self.hp_temp_out_min = {}
        self.hp_temp_out_max = {}
        self.hp_u_value = {}
        self.hp_thermal_resistance = {}
        self.hp_h_rad = {}
        self.hp_area_rad = {}
        self.hp_mass_hw_demand = {}
        self.hp_mass_radiator = {}
        self.hp_t_out = {}

        # P2H
        # Hydrogen sell price
        self._h2_sell = backpack.get('h2_sell')
        self._chp_demand = backpack.get('CHP')
        # Electrolyzer data
        self.sets_electrolyzer = {}  # stores the Meter's electrolyzer ids
        self._eff_ec = {}  # stores the fixed/variable efficiency(ies)
        self._pn = {}  # Rated power for each electrolyzer
        self._pmin_ec = {}  # Minimal power to start for each electrolyzer
        self._power_bounds_ec = {} # Relevant for variable efficiency mode
        self._variable_eff_ec = backpack.get('variable_efficiency_ec', False)
        self._hhv = 39.4  # Defining higher heating value at STP (kWh / kg)
        # H2 tank data
        self.sets_hydrogen_storage = {}  # stores the hydrogen tank ids
        self._h2_capacity = {}
        self._init_h2 = {}
        self._h2_min = {}
        # Fuel cell data
        self.sets_fuel_cell = {} # Sets of fuel cell
        self._pn_fc = {} # Maximum FC power output
        self._pmin_fc = {} # Minimum FC power
        self._eff_fc = {} # May contain a fixed value per meter per fuel_cell_id or list of tuples with slopes and y-intercepts
        self._power_bounds_fc = {} # Relevant for variable efficiency mode
        self._variable_eff_fc = backpack.get('variable_efficiency_fc', False)

    def __define_milp(self):
        """
        Method to define the second stage MILP problem.
        """
        logger.debug(f'-- defining the collective (pool) MILP problem...')

        # Define a minimization MILP
        self.milp = LpProblem(f'stage2', LpMinimize)

        # Additional temporal variables
        self.time_intervals = time_intervals(self._horizon, self._delta_t)
        self.time_series = range(self.time_intervals)

        # Set of Meters
        self.set_meters = list(self._meters_data.keys())

        # For simplicity, unpack Meters' information into lists, by type of data, where each Meter is solely
        # identified by its relative position on the list
        self._l_buy = dict_per_param(self._meters_data, 'l_buy')
        self._l_sell = dict_per_param(self._meters_data, 'l_sell')
        self._e_c = dict_per_param(self._meters_data, 'e_c')
        self._e_g = dict_per_param(self._meters_data, 'e_g')
        self._p_meter_max = dict_per_param(self._meters_data, 'max_p')
        self._big_m = 10 * max(self._p_meter_max.values())
        if self.second_stage:
            self._c_ind = dict_per_param(self._meters_data, 'c_ind')
        else:
            # Unbound the restriction regarding stage 1 cost for single stage runs
            self._c_ind = {k: 1000 for k in self.set_meters}

        # Unpack batteries information
        for n in self.set_meters:
            meter_btm_storage = self._meters_data[n].get('btm_storage', None)
            if not meter_btm_storage:
                self.sets_btm_storage[n] = []
                continue

            self.sets_btm_storage[n] = list(meter_btm_storage.keys())
            self._eff_bc[n] = {b: meter_btm_storage[b]['eff_bc'] for b in self.sets_btm_storage[n]}
            self._eff_bd[n] = {b: meter_btm_storage[b]['eff_bd'] for b in self.sets_btm_storage[n]}
            self._p_max[n] = {b: meter_btm_storage[b]['p_max'] for b in self.sets_btm_storage[n]}
            self._e_bn[n] = {b: meter_btm_storage[b]['e_bn'] for b in self.sets_btm_storage[n]}
            self._soc_min[n] = {b: meter_btm_storage[b]['soc_min'] for b in self.sets_btm_storage[n]}
            self._soc_max[n] = {b: meter_btm_storage[b]['soc_max'] for b in self.sets_btm_storage[n]}
            self._init_e_bat[n] = {b: meter_btm_storage[b]['init_e'] for b in self.sets_btm_storage[n]}
            self._deg_cost[n] = {b: meter_btm_storage[b]['degradation_cost'] for b in self.sets_btm_storage[n]}

        # Unpack EVs information
        for n in self.set_meters:
            meter_btm_ev = self._meters_data[n].get('btm_evs')
            if meter_btm_ev is not None:
                self.sets_btm_ev[n] = list(meter_btm_ev.keys())
                self._trip_ev[n] = {ev: meter_btm_ev[ev]['trip_ev'] for ev in self.sets_btm_ev[n]}
                self._min_energy_storage_ev[n] = {ev: meter_btm_ev[ev]['min_energy_storage_ev'] for ev in
                                                  self.sets_btm_ev[n]}
                self._battery_capacity_ev[n] = {ev: meter_btm_ev[ev]['battery_capacity_ev'] for ev in
                                                self.sets_btm_ev[n]}
                self._eff_bc_ev[n] = {ev: meter_btm_ev[ev]['eff_bc_ev'] for ev in self.sets_btm_ev[n]}
                self._eff_bd_ev[n] = {ev: meter_btm_ev[ev]['eff_bd_ev'] for ev in self.sets_btm_ev[n]}
                self._init_e_ev[n] = {ev: meter_btm_ev[ev]['init_e_ev'] for ev in self.sets_btm_ev[n]}
                self._pmax_c_ev[n] = {ev: meter_btm_ev[ev]['pmax_c_ev'] for ev in self.sets_btm_ev[n]}
                self._pmax_d_ev[n] = {ev: meter_btm_ev[ev]['pmax_d_ev'] for ev in self.sets_btm_ev[n]}
                self._bin_ev[n] = {ev: meter_btm_ev[ev]['bin_ev'] for ev in self.sets_btm_ev[n]}
            else:
                self.sets_btm_ev[n] = []

        # EWH
        # unpack variables
        for n in self.set_meters:
            try:
                self._ewh = self._meters_data[n]['ewh']
            except KeyError:
                self._ewh = None
            if self._ewh is not None:
                self.set_ewh[n] = list(self._ewh.keys())
                self._ewh_paramsInput[n] = {e: self._ewh[e]['params_input'] for e in self.set_ewh[n]}
                self._ewh_dataset[n] = {e: self._ewh[e]['dataset'] for e in self.set_ewh[n]}
            else:
                self.set_ewh[n] = []

        if bool(self._ewh_dataset):
            # create EWH varBackpacks
            from rec_op_lem_prices.ewh.ewh_flex import ewh_preparation
            global varBackpack

            varBackpack = {}
            for n in self.set_meters:
                self._ewh = self._meters_data[n]['ewh']

                if self._ewh is not None:
                    varBackpack[n] = {
                        e: ewh_preparation(self._ewh_paramsInput[n][e], self._ewh_dataset[n][e], resample='1h')
                        for e in self.set_ewh[n]
                    }

                    self.wh_init[n] = {e: varBackpack[n][e]['wh_init'] for e in self.set_ewh[n]}
                    self.ewh_power[n] = {e: varBackpack[n][e]['ewh_power'] for e in self.set_ewh[n]}
                    self.delta_t[n] = {e: varBackpack[n][e]['delta_t'] for e in self.set_ewh[n]}
                    self.ewh_start_temp[n] = {e: varBackpack[n][e]['ewh_start_temp'] for e in self.set_ewh[n]}
                    self.ewh_capacity[n] = {e: varBackpack[n][e]['ewh_capacity'] for e in self.set_ewh[n]}
                    self.waterHeatCap[n] = {e: varBackpack[n][e]['waterHeatCap'] for e in self.set_ewh[n]}
                    self.heatTransferCoeff[n] = {e: varBackpack[n][e]['heatTransferCoeff'] for e in self.set_ewh[n]}
                    self.ewh_area[n] = {e: varBackpack[n][e]['ewh_area'] for e in self.set_ewh[n]}
                    self.ambTemp[n] = {e: varBackpack[n][e]['ambTemp'] for e in self.set_ewh[n]}
                    self.wh_min[n] = {e: varBackpack[n][e]['wh_min'] for e in self.set_ewh[n]}
                    self.wh_max[n] = {e: varBackpack[n][e]['wh_max'] for e in self.set_ewh[n]}
                    self.ewh_min_temp[n] = {e: varBackpack[n][e]['ewh_min_temp'] for e in self.set_ewh[n]}
                    self.ewh_max_temp[n] = {e: varBackpack[n][e]['ewh_max_temp'] for e in self.set_ewh[n]}
                    self.delta_use[n] = {e: varBackpack[n][e]['delta_use'] for e in self.set_ewh[n]}
                    self.tempSet[n] = {e: varBackpack[n][e]['tempSet'] for e in self.set_ewh[n]}
                    self.bigNumber[n] = {e: varBackpack[n][e]['bigNumber'] for e in self.set_ewh[n]}
                    self.regressor_aboveSet_m_temp[n] = \
                        {e: varBackpack[n][e]['regressor_aboveSet_m_temp'] for e in self.set_ewh[n]}
                    self.regressor_aboveSet_m_delta[n] = \
                        {e: varBackpack[n][e]['regressor_aboveSet_m_delta'] for e in self.set_ewh[n]}
                    self.regressor_aboveSet_b[n] = \
                        {e: varBackpack[n][e]['regressor_aboveSet_b'] for e in self.set_ewh[n]}
                    self.regressor_belowSet_m_temp[n] = \
                        {e: varBackpack[n][e]['regressor_belowSet_m_temp'] for e in self.set_ewh[n]}
                    self.regressor_belowSet_m_delta[n] = \
                        {e: varBackpack[n][e]['regressor_belowSet_m_delta'] for e in self.set_ewh[n]}
                    self.regressor_belowSet_b[n] = \
                        {e: varBackpack[n][e]['regressor_belowSet_b'] for e in self.set_ewh[n]}
                else:
                    varBackpack[n] = []

        # Unpack HVAC information
        for n in self.set_meters:
            self._hvac = self._meters_data[n].get('hvac')
            if self._hvac is not None:
                self.set_hvac[n] = list(self._hvac.keys())
                self.mu[n] = {h: self._hvac[h]['mu'] for h in self.set_hvac[n]}
                self.psi[n] = {h: self._hvac[h]['psi'] for h in self.set_hvac[n]}
                self.hvac_capacity[n] = {h: self._hvac[h]['hvac_capacity'] for h in self.set_hvac[n]}
                self.hvac_temp_min[n] = {h: self._hvac[h]['temp_min'] for h in self.set_hvac[n]}
                self.hvac_temp_max[n] = {h: self._hvac[h]['temp_max'] for h in self.set_hvac[n]}
                self.hvac_init_temp[n] = {h: self._hvac[h]['init_temp'] for h in self.set_hvac[n]}
                self.T_out[n] = {h: self._hvac[h]['t_out'] for h in self.set_hvac[n]}
                self.thermal_resist[n] = {h: self._hvac[h]['thermal_resist'] for h in self.set_hvac[n]}
                self.thermal_cap[n] = {h: self._hvac[h]['thermal_cap'] for h in self.set_hvac[n]}
                self.type[n] = {h: self._hvac[h]['type'] for h in self.set_hvac[n]}
            else:
                self.set_hvac[n] = []
        # Unpack HP information
        for n in self.set_meters:
            self._hp = self._meters_data[n].get('hp')
            if self._hp is not None:
                self.set_hp[n] = list(self._hp.keys())
                self.hp_type[n] = {hp: self._hp[hp]['type'] for hp in self.set_hp[n]}
                self.hp_power_rated[n] = {hp: self._hp[hp]['power_rated'] for hp in self.set_hp[n]}
                self.hp_capacity_tank[n] = {hp: self._hp[hp]['capacity_tank'] for hp in self.set_hp[n]}
                self.hp_c_p[n] = {hp: self._hp[hp]['c_p'] for hp in self.set_hp[n]}
                self.hp_temp_inlet[n] = {hp: self._hp[hp]['temp_inlet'] for hp in self.set_hp[n]}
                self.hp_temp_desired[n] = {hp: self._hp[hp]['temp_desired'] for hp in self.set_hp[n]}
                self.hp_temp_out_init[n] = {hp: self._hp[hp]['temp_out_init'] for hp in self.set_hp[n]}
                self.hp_temp_indoor_init[n] = {hp: self._hp[hp]['temp_indoor_init'] for hp in self.set_hp[n]}
                self.hp_temp_indoor_final[n] = {hp: self._hp[hp]['temp_indoor_final'] for hp in self.set_hp[n]}
                self.hp_temp_indoor_min[n] = {hp: self._hp[hp]['temp_indoor_min'] for hp in self.set_hp[n]}
                self.hp_temp_indoor_max[n] = {hp: self._hp[hp]['temp_indoor_max'] for hp in self.set_hp[n]}
                self.hp_temp_out_min[n] = {hp: self._hp[hp]['temp_out_min'] for hp in self.set_hp[n]}
                self.hp_temp_out_max[n] = {hp: self._hp[hp]['temp_out_max'] for hp in self.set_hp[n]}
                self.hp_u_value[n] = {hp: self._hp[hp]['u_value'] for hp in self.set_hp[n]}
                self.hp_thermal_resistance[n] = {hp: self._hp[hp]['thermal_resistance'] for hp in self.set_hp[n]}
                self.hp_h_rad[n] = {hp: self._hp[hp]['h_rad'] for hp in self.set_hp[n]}
                self.hp_area_rad[n] = {hp: self._hp[hp]['area_rad'] for hp in self.set_hp[n]}
                self.hp_mass_hw_demand[n] = {hp: self._hp[hp]['mass_hw_demand'] for hp in self.set_hp[n]}
                self.hp_mass_radiator[n] = {hp: self._hp[hp]['mass_radiator'] for hp in self.set_hp[n]}
                self.hp_t_out[n] = {hp: self._hp[hp]['t_out'] for hp in self.set_hp[n]}
            else:
                self.set_hp[n] = []

        tank_links = {}

        for n in self.set_meters:
            # Extract components for this node
            electrolyzer = self._meters_data[n].get('electrolyzer', {})
            h2tank = self._meters_data[n].get('h2_tank', {})
            fuel_cell = self._meters_data[n].get('fuel_cell', {})

            # Initialize sets
            self.sets_electrolyzer[n] = list(electrolyzer.keys()) if electrolyzer else []
            self.sets_hydrogen_storage[n] = list(h2tank.keys()) if h2tank else []
            self.sets_fuel_cell[n] = list(fuel_cell.keys()) if fuel_cell else []

            # Store tank parameters
            if h2tank:
                self._h2_capacity[n] = {tid: h2tank[tid]["capacity"] for tid in self.sets_hydrogen_storage[n]}
                self._init_h2[n] = {tid: h2tank[tid]["init_h2"] for tid in self.sets_hydrogen_storage[n]}
                self._h2_min[n] = {tid: h2tank[tid]["h2_min"] for tid in self.sets_hydrogen_storage[n]}
            else:
                self._h2_capacity[n] = {}
                self._init_h2[n] = {}
                self._h2_min[n] = {}

            # Store electrolyzer parameters
            if electrolyzer:
                self._pn[n], self._pmin_ec[n], self._eff_ec[n] = {}, {}, {}
                for e in self.sets_electrolyzer[n]:
                    self._pn[n][e] = electrolyzer[e]['pn']
                    self._pmin_ec[n][e] = electrolyzer[e]['p_min']
                    if self._variable_eff_ec:
                        self._power_bounds_ec[n] = {}
                        slope_intercepts, power_bounds = piecewise_linearization(electrolyzer[e])
                        self._eff_ec[n][e] = slope_intercepts
                        self._power_bounds_ec[n][e] = power_bounds
                    else:
                        self._eff_ec[n] = {e: electrolyzer[e]['eff'] for e in self.sets_electrolyzer[n]}
            else:
                self._pn[n], self._pmin_ec[n], self._eff_ec[n] = {}, {}, {}

            # Store fuel cell parameters
            if fuel_cell:
                self._pn_fc[n], self._pmin_fc[n], self._eff_fc[n] = {}, {}, {}
                for fc in self.sets_fuel_cell[n]:
                    self._pn_fc[n][fc] = fuel_cell[fc]['pn']
                    self._pmin_fc[n][fc] = fuel_cell[fc]['p_min']
                    if self._variable_eff_fc:
                        self._power_bounds_fc[n] = {}
                        slope_intercepts, power_bounds = piecewise_linearization(fuel_cell[fc])
                        self._eff_fc[n][fc] = slope_intercepts
                        self._power_bounds_fc[n][fc] = power_bounds
                    else:
                        self._eff_fc[n] = {fc: fuel_cell[fc]['eff'] for fc in self.sets_fuel_cell[n]}
            else:
                self._pn_fc[n], self._pmin_fc[n], self._eff_fc[n] = {}, {}, {}

            # --- Build tank_links for this node ---
            tank_links[n] = {tid: {"EC": [], "FC": []} for tid in self.sets_hydrogen_storage[n]}

            # Assign electrolyzers to their tanks
            for ec in self.sets_electrolyzer[n]:
                tid = electrolyzer[ec]["link"]
                if tid in tank_links[n]:
                    tank_links[n][tid]["EC"].append(ec)

            # Assign fuel cells to their tanks
            for fc in self.sets_fuel_cell[n]:
                tid = fuel_cell[fc]["link"]
                if tid in tank_links[n]:
                    tank_links[n][tid]["FC"].append(fc)

        # Initialize the decision variables
        # energy supplied to n from its retailer [kWh]
        e_sup_retail = dict_none_lists(self.time_intervals, self.set_meters)
        # energy surplus sold by n to its retailer [kWh]
        e_sur_retail = dict_none_lists(self.time_intervals, self.set_meters)
        # energy supplied to n at a market-indexed price [kWh]
        e_sup_market = dict_none_lists(self.time_intervals, self.set_meters)
        # energy surplus sold by n at a market-indexed price [kWh]
        e_sur_market = dict_none_lists(self.time_intervals, self.set_meters)
        # when True allows supply when false allows surplus
        delta_sup = dict_none_lists(self.time_intervals, self.set_meters)
        # energy bought locally by n
        e_pur = dict_none_lists(self.time_intervals, self.set_meters)
        # energy sold locally by n
        e_sale = dict_none_lists(self.time_intervals, self.set_meters)
        # net consumption at meter n [kWh]
        e_cmet = dict_none_lists(self.time_intervals, self.set_meters)
        # energy self-consumed by n (in theory, g.t.e. that value)
        e_slc = dict_none_lists(self.time_intervals, self.set_meters)
        # consumption at meter n (in theory, g.t.e. that value)
        e_consumed = dict_none_lists(self.time_intervals, self.set_meters)
        # consumed energy bought locally by n (in theory, g.t.e. that value)
        e_alc = dict_none_lists(self.time_intervals, self.set_meters)
        # auxiliary binary variable for defining self-consumed energy by n
        delta_slc = dict_none_lists(self.time_intervals, self.set_meters)
        # for defining e_consumed when a particular self._l_grid[t] is negative
        delta_cmet = dict_none_lists(self.time_intervals, self.set_meters)
        # for defining e_alc when a particular self._l_grid[t] is negative
        delta_alc = dict_none_lists(self.time_intervals, self.set_meters)
        # extra power flow at n, beyond p_meter_max [kW]
        p_extra = dict_none_lists(self.time_intervals, self.set_meters)
        # energy stored by the batteries of n [kWh]
        e_bat = {n: dict_none_lists(self.time_intervals, self.sets_btm_storage[n]) for n in self.set_meters}
        # SOC of the batteries of n [%]
        soc_bat = {n: dict_none_lists(self.time_intervals, self.sets_btm_storage[n]) for n in self.set_meters}
        # energy charged by n's batteries [kWh]
        e_bc = {n: dict_none_lists(self.time_intervals, self.sets_btm_storage[n]) for n in self.set_meters}
        # energy discharged by n's batteries [kWh]
        e_bd = {n: dict_none_lists(self.time_intervals, self.sets_btm_storage[n]) for n in self.set_meters}
        # when True allows charge, else discharge
        delta_bc = {n: dict_none_lists(self.time_intervals, self.sets_btm_storage[n]) for n in self.set_meters}
        # EV decision variables
        # energy stored in ev [kWh]
        ev_stored = {n: dict_none_lists(self.time_intervals, self.sets_btm_ev[n]) for n in self.set_meters}
        # power charge of ev [kW]
        p_ev_charge = {n: dict_none_lists(self.time_intervals, self.sets_btm_ev[n]) for n in self.set_meters}
        # power discharge of ev [kW]
        p_ev_discharge = {n: dict_none_lists(self.time_intervals, self.sets_btm_ev[n]) for n in self.set_meters}
        # EWH - Initialize decision variables
        if bool(self._ewh_dataset):
            temp = {n: dict_none_lists(self.time_intervals, self.set_ewh[n]) for n in self.set_meters}
            w_tot = {n: dict_none_lists(self.time_intervals, self.set_ewh[n]) for n in self.set_meters}
            w_in = {n: dict_none_lists(self.time_intervals, self.set_ewh[n]) for n in self.set_meters}
            w_loss = {n: dict_none_lists(self.time_intervals, self.set_ewh[n]) for n in self.set_meters}
            delta_in = {n: dict_none_lists(self.time_intervals, self.set_ewh[n]) for n in self.set_meters}
            w_water = {n: dict_none_lists(self.time_intervals, self.set_ewh[n]) for n in self.set_meters}
            costComfort = {n: dict_none_lists(self.time_intervals, self.set_ewh[n]) for n in self.set_meters}
            binAux = {n: dict_none_lists(self.time_intervals, self.set_ewh[n]) for n in self.set_meters}
            energyEWH = {n: dict_none_lists(self.time_intervals, self.set_ewh[n]) for n in self.set_meters}
        # HVAC - Initialize decision variables
        if self.set_hvac is not None:
            hvac_temp = {n: dict_none_lists(self.time_intervals, self.set_hvac[n]) for n in self.set_meters}
            hvac_power = {n: dict_none_lists(self.time_intervals, self.set_hvac[n]) for n in self.set_meters}
            delta_hvac = {n: dict_none_lists(self.time_intervals, self.set_hvac[n]) for n in self.set_meters}
            hvac_active = {n: dict_none_lists(self.time_intervals, self.set_hvac[n]) for n in self.set_meters}
            hvac_cost_comfort = {n: dict_none_lists(self.time_intervals, self.set_hvac[n]) for n in self.set_meters}
            hvac_mode = {n: dict_none_lists(self.time_intervals, self.set_hvac[n]) for n in self.set_meters}
            hvac_mode_heat = {n: dict_none_lists(self.time_intervals, self.set_hvac[n]) for n in self.set_meters}
            hvac_mode_off = {n: dict_none_lists(self.time_intervals, self.set_hvac[n]) for n in self.set_meters}
            hvac_mode_cool = {n: dict_none_lists(self.time_intervals, self.set_hvac[n]) for n in self.set_meters}

        # HP - Initialize decision variables
        if self.set_hvac is not None:
            self.hp_temp_indoor = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.hp_temp_outlet = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.hp_power = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.hp_active = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.hp_cost_comfort = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.hp_op_mode = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.heating_kwh = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.circulation_kw = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.tank_heating_kwh = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.hp_temp_return = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}
            self.hp_lost_power = {n: dict_none_lists(self.time_intervals, self.set_hp[n]) for n in self.set_meters}

        # Electrolyzer
        # energy input toward the electrolyzer
        e_ec_total = {n: dict_none_lists(self.time_intervals, self.sets_electrolyzer[n]) for n in self.set_meters}
        # mass of hydrogen produced by an electrolyzer
        m_h2 = {n: dict_none_lists(self.time_intervals, self.sets_electrolyzer[n]) for n in self.set_meters}
        # when producing
        delta_ec_on = {n: dict_none_lists(self.time_intervals, self.sets_electrolyzer[n]) for n in self.set_meters}

        # Hydrogen storage
        # energy stored in the hydrogen tank
        h2_storage = {n: dict_none_lists(self.time_intervals, self.sets_hydrogen_storage[n]) for n in self.set_meters}
        # mass of hydrogen exported from the hydrogen tank
        m_chp = {n: dict_none_lists(self.time_intervals, self.sets_hydrogen_storage[n]) for n in self.set_meters}

        # Fuel cell
        # energy directed toward the fuel cell
        m_fc = {n: dict_none_lists(self.time_intervals, self.sets_fuel_cell[n]) for n in self.set_meters}
        e_fc_total = {n: dict_none_lists(self.time_intervals, self.sets_fuel_cell[n]) for n in self.set_meters}
        delta_fc_on = {n: dict_none_lists(self.time_intervals, self.sets_fuel_cell[n]) for n in self.set_meters}

        if self._variable_eff_ec:
            b_ec_s = {}
            e_ec_s = {}

            for n in self.set_meters:
                b_ec_s[n] = {}
                e_ec_s[n] = {}

                for ec in self.sets_electrolyzer[n]:
                    num_intercepts = len(self._eff_ec[n][ec])
                    seg_keys = [f"s{i + 1}" for i in range(num_intercepts)]

                    e_ec_s[n][ec] = {k: none_lists(self.time_intervals) for k in seg_keys}
                    b_ec_s[n][ec] = {k: none_lists(self.time_intervals) for k in seg_keys}

        if self._variable_eff_fc:
            b_fc_s = {}
            e_fc_s = {}

            for n in self.set_meters:
                b_fc_s[n] = {}
                e_fc_s[n] = {}

                for fc in self.sets_fuel_cell[n]:
                    num_intercepts = len(self._eff_fc[n][fc])
                    seg_keys = [f"s{i + 1}" for i in range(num_intercepts)]

                    e_fc_s[n][fc] = {k: none_lists(self.time_intervals) for k in seg_keys}
                    b_fc_s[n][fc] = {k: none_lists(self.time_intervals) for k in seg_keys}

        if self.strict_pos_coeffs:
            # auxiliary binary variable for imposing positive allocation coefficients
            delta_coeff = dict_none_lists(self.time_intervals, self.set_meters)
        if self.total_share_coeffs:
            # auxiliary binary variable for signaling if the REC has a surplus or a deficit
            delta_rec_balance = none_lists(self.time_intervals)
            # auxiliary binary variable for signaling if a meter has a surplus or a deficit
            delta_meter_balance = dict_none_lists(self.time_intervals, self.set_meters)

        # Define the decision variables as puLP objets
        if self.total_share_coeffs:
            for t in self.time_series:
                increment = f't{t:03d}'
                delta_rec_balance[t] = LpVariable('delta_rec_balance_' + increment, cat=LpBinary)

        t_n_series = itertools.product(self.set_meters, self.time_series)  # iterates over each Meter and each time step
        for n, t in t_n_series:
            increment = f'{n}_t{t:03d}'
            e_sup_retail[n][t] = LpVariable('e_sup_retail_' + increment, lowBound=0)
            e_sur_retail[n][t] = LpVariable('e_sur_retail_' + increment, lowBound=0)
            e_sup_market[n][t] = LpVariable('e_sup_market_' + increment, lowBound=0)
            e_sur_market[n][t] = LpVariable('e_sur_market_' + increment, lowBound=0)
            delta_sup[n][t] = LpVariable('delta_sup_' + increment, cat=LpBinary)
            e_pur[n][t] = LpVariable('e_pur_pool_' + increment, lowBound=0)
            e_sale[n][t] = LpVariable('e_sale_pool_' + increment, lowBound=0)
            e_cmet[n][t] = LpVariable('e_cmet_' + increment)
            e_slc[n][t] = LpVariable('e_slc_pool_' + increment, lowBound=0)
            e_consumed[n][t] = LpVariable('e_consumed_' + increment, lowBound=0)
            e_alc[n][t] = LpVariable('e_alc_' + increment, lowBound=0)
            delta_slc[n][t] = LpVariable('delta_slc_' + increment, cat=LpBinary)
            delta_cmet[n][t] = LpVariable('delta_cmet_' + increment, cat=LpBinary)
            delta_alc[n][t] = LpVariable('delta_alc_' + increment, cat=LpBinary)
            p_extra[n][t] = LpVariable('p_extra_' + increment, lowBound=0)
            if self.strict_pos_coeffs:
                delta_coeff[n][t] = LpVariable('delta_coeff_' + increment, cat=LpBinary)
            if self.total_share_coeffs:
                delta_meter_balance[n][t] = LpVariable('delta_meter_balance_' + increment, cat=LpBinary)
            for b in self.sets_btm_storage[n]:
                increment = f'{n}_{b}_t{t:03d}'
                e_bat[n][b][t] = LpVariable('e_bat_' + increment, lowBound=0)
                soc_bat[n][b][t] = LpVariable('soc_bat_' + increment, lowBound=0)
                e_bc[n][b][t] = LpVariable('e_bc_' + increment, lowBound=0)
                e_bd[n][b][t] = LpVariable('e_bd_' + increment, lowBound=0)
                delta_bc[n][b][t] = LpVariable('delta_bc_' + increment, cat=LpBinary)
            for ev in self.sets_btm_ev[n]:
                increment = f'{n}_{ev}_t{t:03d}'
                ev_stored[n][ev][t] = LpVariable('ev_stored_' + increment, lowBound=0)
                p_ev_charge[n][ev][t] = LpVariable('p_ev_charge_' + increment, lowBound=0)
                p_ev_discharge[n][ev][t] = LpVariable('p_ev_discharge_' + increment, lowBound=0)

            for ec in self.sets_electrolyzer[n]:
                increment = f'{n}_{ec}_t{t:05d}'
                m_h2[n][ec][t] = LpVariable('m_h2_' + increment, lowBound=0)
                delta_ec_on[n][ec][t] = LpVariable('delta_ec_on_' + increment, cat=LpBinary)
                e_ec_total[n][ec][t] = LpVariable('e_ec_total_' + increment, lowBound=0)
                if self._variable_eff_ec:
                    for s in e_ec_s[n][ec]:
                        e_ec_s[n][ec][s][t] = LpVariable(f'e_{n}_{ec}_s{s}_{increment}', lowBound=0)
                    for s in b_ec_s[n][ec]:
                        b_ec_s[n][ec][s][t] = LpVariable(f'b_{n}_{ec}_s{s}_{increment}', cat=LpBinary)

            for h2 in self.sets_hydrogen_storage[n]:
                increment = f'{n}_{h2}_t{t:05d}'
                h2_storage[n][h2][t] = LpVariable('h2_storage_' + increment, lowBound=0)
                m_chp[n][h2][t] = LpVariable('m_chp_' + increment, lowBound=0)
            for fc in self.sets_fuel_cell[n]:
                increment = f'{n}_{fc}_t{t:05d}'
                m_fc[n][fc][t] = LpVariable('m_fc_' + increment, lowBound=0)
                e_fc_total[n][fc][t] = LpVariable('e_fc_total_' + increment, lowBound=0)
                delta_fc_on[n][fc][t] = LpVariable('delta_fc_on_' + increment, lowBound=0, cat=LpBinary)
                if self._variable_eff_fc:
                    for s in e_fc_s[n][fc]:
                        # Unique variable names by adding segment index
                        e_fc_s[n][fc][s][t] = LpVariable(f'e_{n}_{fc}_s{s}_{increment}', lowBound=0)
                    for s in b_fc_s[n][fc]:
                        b_fc_s[n][fc][s][t] = LpVariable(f'b_{n}_{fc}_s{s}_{increment}', cat=LpBinary)

            # EWH decision variables
            if bool(self._ewh_dataset):
                for e in self.set_ewh[n]:
                    increment = f'{n}_{e}_t{t:07d}'
                    # Temperature of water at EWH outlet at the beginning of time interval t (°C)
                    temp[n][e][t] = LpVariable(f'temp_' + increment, lowBound=0)
                    # Total energy balance of prosumer’s EWH at time interval t (kWh)
                    w_tot[n][e][t] = LpVariable(f'w_tot_' + increment, lowBound=0)
                    # Energy into the prosumer’s EWH at time interval t (kWh)
                    w_in[n][e][t] = LpVariable(f'w_in_' + increment, lowBound=0)
                    # Thermal energy losses at time interval t (kWh)
                    w_loss[n][e][t] = LpVariable(f'w_loss_' + increment)
                    # Binary variable for EWH operation status (1 = ON, 0 = OFF)
                    delta_in[n][e][t] = LpVariable(f'delta_in_' + increment, cat=LpBinary)
                    # Amount of energy stored in the EWH after usage and mixing with inlet
                    w_water[n][e][t] = LpVariable(f'w_water_' + increment, lowBound=0)
                    # Extra cost associated with water temperature reaching below comfort
                    costComfort[n][e][t] = LpVariable(f'costComfort_' + increment, lowBound=0)
                    # Binary Variable for if-else expression 15
                    binAux[n][e][t] = LpVariable(f'binAux_' + increment, cat=LpBinary)
                    # Pricing of that specific energy usage
                    energyEWH[n][e][t] = LpVariable(f'energyEWH_' + increment, lowBound=0)
            if self.set_hvac is not None:
                for h in self.set_hvac[n]:
                    increment = f'{n}_{h}_t{t:03d}'
                    hvac_temp[n][h][t] = LpVariable(f'hvac_temp_' + increment, lowBound=0)
                    hvac_power[n][h][t] = LpVariable(f'hvac_power_' + increment, lowBound=0)
                    delta_hvac[n][h][t] = LpVariable(f'delta_hvac_' + increment, lowBound=0, upBound=5, cat=LpInteger)
                    hvac_active[n][h][t] = LpVariable(f'hvac_active_' + increment, cat=LpBinary)
                    hvac_mode[n][h][t] = LpVariable(f'hvac_mode_' + increment, cat=LpBinary)
                    hvac_mode_heat[n][h][t] = LpVariable(f'hvac_mode_heat_' + increment, cat=LpBinary)
                    hvac_mode_off[n][h][t] = LpVariable(f'hvac_mode_off_' + increment, cat=LpBinary)
                    hvac_mode_cool[n][h][t] = LpVariable(f'hvac_mode_cool_' + increment, cat=LpBinary)
                    hvac_cost_comfort[n][h][t] = LpVariable(f'hvac_cost_comfort_' + increment, lowBound=0)

            if self.set_hp is not None:
                for hp in self.set_hp[n]:
                    increment = f'{n}_{hp}_t{t:03d}'
                    self.hp_temp_indoor[n][hp][t] = LpVariable(f'hp_temp_indoor_' + increment, lowBound=0)
                    self.hp_temp_outlet[n][hp][t] = LpVariable(f'hp_temp_outlet_' + increment, lowBound=0)
                    self.hp_power[n][hp][t] = LpVariable(f'power_hp_' + increment, lowBound=0)
                    self.hp_active[n][hp][t] = LpVariable(f'hp_active_' + increment, cat=LpBinary)
                    self.hp_cost_comfort[n][hp][t] = LpVariable(f'hp_cost_comfort_' + increment, lowBound=0)
                    self.hp_active[n][hp][t] = LpVariable(f'hp_active_' + increment, cat=LpBinary)
                    self.heating_kwh[n][hp][t] = LpVariable(f'hp_power_heating_' + increment, lowBound=0)
                    self.circulation_kw[n][hp][t] = LpVariable(f'hp_power_circulation_' + increment, lowBound=0)
                    self.tank_heating_kwh[n][hp][t] = LpVariable(f'hp_power_tank_' + increment, lowBound=0)
                    self.hp_temp_return[n][hp][t] = LpVariable(f'hp_temp_return_' + increment, lowBound=0)
                    self.hp_lost_power[n][hp][t] = LpVariable(f'hp_lost_power_' + increment, lowBound=0)

        # Eq. 10: Objective Function
        objective = lpSum(
            lpSum(
                e_sup_retail[n][t] * self._l_buy[n][t] - e_sur_retail[n][t] * self._l_sell[n][t]
                + e_sup_market[n][t] * self._l_market_buy[t] - e_sur_market[n][t] * self._l_market_sell[t]
                + e_slc[n][t] * self._l_grid[t]
                + p_extra[n][t] * self._l_extra
                + lpSum(self._deg_cost[n][b] * e_bd[n][b][t] for b in self.sets_btm_storage[n])
                + lpSum(costComfort[n][e][t] * 100 for e in self.set_ewh[n])
                for n in self.set_meters
            )
            for t in self.time_series
        )
        for t in self.time_series:
            for n in self.set_meters:
                if t != 0:
                    objective += lpSum(hvac_cost_comfort[n][h][t] * 2 for h in self.set_hvac[n]) + lpSum(
                        self.hp_cost_comfort[n][hp][t] * 1 for hp in self.set_hp[n])

        for n_tank, t in itertools.product(self.sets_hydrogen_storage, self.time_series):
            objective -= lpSum(m_chp[n_tank][tank][t] * self._h2_sell[t] for tank in self.sets_hydrogen_storage[n_tank])

        self.milp += objective, 'Objective Function'

        # Eq. 11-31: Constraints
        for t in self.time_series:
            increment = f'{t:03d}'

            # Eq. 11
            self.milp += \
                lpSum(e_sale[n][t] for n in self.set_meters) == lpSum(e_pur[n][t] for n in self.set_meters), \
                'Market_equilibrium_' + increment

            if self.total_share_coeffs:
                # Eq. 32
                self.milp += \
                    lpSum(e_cmet[n][t] for n in self.set_meters) >= - self._big_m * delta_rec_balance[t], \
                    'Check_REC_surplus_' + increment

                # Eq. 33
                self.milp += \
                    lpSum(e_cmet[n][t] for n in self.set_meters) <= self._big_m * (1 - delta_rec_balance[t]), \
                    'Check_REC_deficit_' + increment

        for n, t in itertools.product(self.set_meters, self.time_series):
            increment = f'{n}_t{t:03d}'

            # Eq. 12
            self.milp += \
                e_cmet[n][t] == \
                e_sup_retail[n][t] + e_sup_market[n][t] + e_pur[n][t] \
                - e_sur_retail[n][t] - e_sur_market[n][t] - e_sale[n][t], \
                'Equilibrium_' + increment

            # Eq. 13
            # UPDATED WITH DISAGREGGATED EWH MODULES (ORIGINAL AND OPTIMIZED LOADS)
            self.milp += \
                (e_cmet[n][t] == self._e_c[n][t] - self._e_g[n][t]
                 + lpSum(e_bc[n][b][t] - e_bd[n][b][t] for b in self.sets_btm_storage[n])
                 + lpSum(p_ev_charge[n][ev][t] - p_ev_discharge[n][ev][t]
                         for ev in self.sets_btm_ev[n])
                 + lpSum(- varBackpack[n][e]['original_load'][t] + energyEWH[n][e][t] for e in self.set_ewh[n]) +
                 lpSum(hvac_power[n][h][t] * self._delta_t for h in self.set_hvac[n]) + lpSum(
                    self.hp_power[n][hp][t] for hp in self.set_hp[n]) +
                 lpSum(e_ec_total[n][ec][t] for ec in self.sets_electrolyzer[n]) -
                 lpSum(e_fc_total[n][fc][t] for fc in self.sets_fuel_cell[n]),
                 'C_met_' + increment)

            # Eq. 14
            self.milp += \
                - p_extra[n][t] - self._p_meter_max[n] <= e_cmet[n][t] * 1 / self._delta_t, \
                'P_flow_low_limit_' + increment

            self.milp += \
                e_cmet[n][t] * 1 / self._delta_t <= p_extra[n][t] + self._p_meter_max[n], \
                'P_flow_high_limit_' + increment

            # Eq. 15
            self.milp += \
                e_sup_retail[n][t] + e_sup_market[n][t] <= self._big_m * delta_sup[n][t], \
                'Supply_ON_' + increment

            self.milp += \
                e_sur_retail[n][t] + e_sur_market[n][t] <= self._big_m * (1 - delta_sup[n][t]), \
                'Supply_OFF_' + increment

            if self._l_grid[t] >= 0:
                # Eq. 20
                self.milp += \
                    e_consumed[n][t] >= e_cmet[n][t], \
                    'Consumption_' + increment

                # Eq. 21
                self.milp += \
                    e_alc[n][t] >= e_pur[n][t] - e_sale[n][t], \
                    'Allocated_energy_' + increment

                # Eq. 22
                self.milp += \
                    e_slc[n][t] >= e_consumed[n][t] - self._big_m * (1 - delta_slc[n][t]), \
                    'Self_consumption_1_' + increment

                # Eq. 23
                self.milp += \
                    e_slc[n][t] >= e_alc[n][t] - self._big_m * delta_slc[n][t], \
                    'Self_consumption_2_' + increment

                # Eq. aux
                self.milp += \
                    delta_cmet[n][t] == 0, \
                    'Consumption_bin_' + increment

                # Eq. aux
                self.milp += \
                    delta_alc[n][t] == 0, \
                    'Allocated_energy_bin_' + increment

            else:
                # Eq. 24
                self.milp += \
                    e_consumed[n][t] <= e_cmet[n][t] + self._big_m * delta_cmet[n][t], \
                    'Consumption_1_' + increment

                # Eq. 25
                self.milp += \
                    e_consumed[n][t] <= self._big_m * (1 - delta_cmet[n][t]), \
                    'Consumption_2_' + increment

                # Eq. 26
                self.milp += \
                    e_alc[n][t] <= e_pur[n][t] - e_sale[n][t] + self._big_m * delta_alc[n][t], \
                    'Allocated_energy_1_' + increment

                # Eq. 27
                self.milp += \
                    e_alc[n][t] <= self._big_m * (1 - delta_alc[n][t]), \
                    'Allocated_energy_2_' + increment

                # Eq. 28
                self.milp += \
                    e_slc[n][t] <= e_consumed[n][t], \
                    'Self_consumption_1_' + increment

                # Eq. 29
                self.milp += \
                    e_slc[n][t] <= e_alc[n][t], \
                    'Self_consumption_2_' + increment

                # Eq. aux
                self.milp += \
                    delta_slc[n][t] == 0, \
                    'Self_consumed_energy_bin_' + increment

            if self.strict_pos_coeffs:
                # Eq. 30
                self.milp += \
                    e_sale[n][t] - e_pur[n][t] <= -e_cmet[n][t] + self._big_m * delta_coeff[n][t], \
                    'Positive_coefficients_1_' + increment

                # Eq. 31
                self.milp += \
                    e_sale[n][t] - e_pur[n][t] <= self._big_m * (1 - delta_coeff[n][t]), \
                    'Positive_coefficients_2_' + increment

            if self.total_share_coeffs:
                # Eq. 34
                self.milp += \
                    e_cmet[n][t] >= - self._big_m * delta_meter_balance[n][t], \
                    'Check_meter_surplus_' + increment

                # Eq. 35
                self.milp += \
                    e_cmet[n][t] <= self._big_m * (1 - delta_meter_balance[n][t]), \
                    'Check_meter_deficit_' + increment

                # Eq. 36
                self.milp += \
                    e_sale[n][t] >= - e_cmet[n][t] - self._big_m * (
                            1 - delta_meter_balance[n][t] + delta_rec_balance[t]), \
                    'Share_all_surplus_low_' + increment

                # Eq. 37
                self.milp += \
                    e_sale[n][t] <= - e_cmet[n][t] + self._big_m * (
                            1 - delta_meter_balance[n][t] + delta_rec_balance[t]), \
                    'Share_all_surplus_high_' + increment

                # Eq. 38
                self.milp += \
                    e_pur[n][t] >= e_cmet[n][t] - self._big_m * (
                            1 - delta_rec_balance[t] + delta_meter_balance[n][t]), \
                    'Buy_all_deficit_low_' + increment

                # Eq. 39
                self.milp += \
                    e_pur[n][t] <= e_cmet[n][t] + self._big_m * (
                            1 - delta_rec_balance[t] + delta_meter_balance[n][t]), \
                    'Buy_all_deficit_high_' + increment

            for b in self.sets_btm_storage[n]:
                increment = f'{n}_{b}_t{t:03d}'

                if self._e_bn[n][b] > 0:
                    # Eq. 16
                    energy_update = e_bc[n][b][t] * self._eff_bc[n][b] \
                                    - e_bd[n][b][t] * 1 / self._eff_bd[n][b]
                    if t == 0:
                        self.milp += \
                            e_bat[n][b][t] == self._init_e_bat[n][b] + energy_update, \
                            'SOC_update_' + increment
                    else:
                        self.milp += \
                            e_bat[n][b][t] == e_bat[n][b][t - 1] + energy_update, \
                            'SOC_update_' + increment

                    # Eq. 17
                    self.milp += \
                        soc_bat[n][b][t] == e_bat[n][b][t] * 100 / self._e_bn[n][b], \
                        'Energy_to_SOC_' + increment

                    self.milp += \
                        soc_bat[n][b][t] >= self._soc_min[n][b], \
                        'Minimum_SOC_' + increment

                    self.milp += \
                        soc_bat[n][b][t] <= self._soc_max[n][b], \
                        'Maximum_SOC_' + increment

                    # Eq. 18
                    self.milp += \
                        e_bc[n][b][t] * 1 / self._delta_t <= self._p_max[n][b] * delta_bc[n][b][t], \
                        'Charge_rate_limit_' + increment

                    self.milp += \
                        e_bd[n][b][t] * 1 / self._delta_t <= self._p_max[n][b] * (1 - delta_bc[n][b][t]), \
                        'Discharge_rate_limit' + increment

            # EVs constraints
            for ev in self.sets_btm_ev[n]:
                increment = f'{n}_{ev}_t{t:03d}'
                # Eq. 41
                if t == 0:
                    self.milp += ev_stored[n][ev][t] == self._init_e_ev[n][ev] + self._eff_bc_ev[n][ev] * \
                                 p_ev_charge[n][ev][t] \
                                 - (1 / self._eff_bd_ev[n][ev]) * p_ev_discharge[n][ev][t] \
                                 - self._trip_ev[n][ev][t], \
                                 'EV_balance_' + increment
                else:
                    self.milp += ev_stored[n][ev][t] == ev_stored[n][ev][t - 1] + self._eff_bc_ev[n][ev] * \
                                 p_ev_charge[n][ev][
                                     t] - (1 / self._eff_bd_ev[n][ev]) * p_ev_discharge[n][ev][t] - \
                                 self._trip_ev[n][ev][t], \
                                 'EV_balance_' + increment

                # Eq. 42
                self.milp += (1 / self._eff_bd_ev[n][ev]) * p_ev_discharge[n][ev][t] <= self._pmax_d_ev[n][ev] * \
                             self._bin_ev[n][ev][t] * self._delta_t, 'EV_Discharging_limit_' + increment

                # Eq. 43
                self.milp += self._eff_bc_ev[n][ev] * p_ev_charge[n][ev][t] <= self._pmax_c_ev[n][ev] * \
                             self._bin_ev[n][ev][t] * self._delta_t, 'EV_Charging_limit_' + increment

                # Eq. 44
                self.milp += ev_stored[n][ev][t] <= self._battery_capacity_ev[n][ev], 'EV_Max_capacity_' + increment

                # Eq. 45
                self.milp += ev_stored[n][ev][t] >= self._min_energy_storage_ev[n][ev], 'EV_Min_capacity_' + increment

        # EWH constraints
        if bool(self._ewh_dataset):
            for n, t in itertools.product(self.set_meters, self.time_series):
                for e in self.set_ewh[n]:
                    # Eq. (1)
                    if t == 0:
                        self.milp += w_tot[n][e][t] == self.wh_init[n][e], \
                            f'Constraint_1_{n}_{e}_{t:07d}'
                    else:
                        self.milp += w_tot[n][e][t] == w_water[n][e][t - 1] + w_in[n][e][t - 1] - w_loss[n][e][t - 1], \
                            f'Constraint_1_{n}_{e}_{t:07d}'
                    # Eq. (2)
                    self.milp += \
                        w_in[n][e][t] == \
                        self.ewh_power[n][e] * self.delta_t[n][e] * delta_in[n][e][t] * self.delta_t[n][e] * 60, \
                            f'Constraint_2_{n}_{e}_{t:07d}'
                    # Eq. (3) Pricing/Energy
                    self.milp += energyEWH[n][e][t] == delta_in[n][e][t] * self.ewh_power[n][e] * self.delta_t[n][e], \
                        f'Constraint_3_{n}_{e}_{t:07d}'
                    # Eq. (4)
                    if t == 0:
                        self.milp += temp[n][e][t] == self.ewh_start_temp[n][e], f'Constraint_4_{n}_{e}_{t:07d}'
                    else:
                        self.milp += \
                            temp[n][e][t] == \
                            w_tot[n][e][t] * 3600 / \
                            (self.delta_t[n][e] * 60) / \
                            (self.ewh_capacity[n][e] * self.waterHeatCap[n][e]), \
                                f'Constraint_4_{n}_{e}_{t:07d}'
                    # Eq. (5)
                    self.milp += \
                        w_loss[n][e][t] == \
                        self.heatTransferCoeff[n][e] * \
                        self.ewh_area[n][e] * \
                        (temp[n][e][t] - self.ambTemp[n][e]) * \
                        self.delta_t[n][e] * \
                        self.delta_t[n][e] * 60, \
                            f'Constraint_5_{n}_{e}_{t:07d}'
                    # Eq. (6)
                    self.milp += self.wh_min[n][e] <= w_tot[n][e][t], f'Constraint_6.1_{n}_{e}_{t:07d}'
                    self.milp += w_tot[n][e][t] <= self.wh_max[n][e], f'Constraint_6.2_{n}_{e}_{t:07d}'
                    self.milp += self.ewh_min_temp[n][e] <= temp[n][e][t], f'Constraint_6.3_{n}_{e}_{t:07d}'
                    self.milp += temp[n][e][t] <= self.ewh_max_temp[n][e], f'Constraint_6.4_{n}_{e}_{t:07d}'

                    # Eq.(7) assure that in the (t) period after the end of hot water usage (t-1),
                    # the EWH has, at least, 80L @ 45ºC [n][e][t]
                    if (self.delta_use[n][e][t] - self.delta_use[n][e][t - 1] != 0) & \
                            (self.delta_use[n][e][t] - self.delta_use[n][e][t - 1] == -self.delta_use[n][e][t - 1]):
                        # if delta_use[n][e][t] - delta_use[t-1] < 0:
                        self.milp += \
                            w_tot[n][e][t] >= \
                            self.tempSet[n][e] * 1.005 * \
                            self.ewh_capacity[n][e] * \
                            self.waterHeatCap[n][e] / 3600 * \
                            self.delta_t[n][e] * 60 - \
                            costComfort[n][e][t], \
                                f'Constraint_7.1_{n}_{e}_{t:07d}'
                        self.milp += \
                            w_tot[n][e][t - 1] >= \
                            self.tempSet[n][e] * 1.005 * \
                            self.ewh_capacity[n][e] * \
                            self.waterHeatCap[n][e] / 3600 * \
                            self.delta_t[n][e] * 60 - \
                            costComfort[n][e][t - 1], \
                                f'Constraint_7.2_{n}_{e}_{t:07d}'

                    # Eq.(8) Internal water energy after usage
                    if self.delta_use[n][e][t] > 0:
                        # binary definition with temp[n][e][t]
                        self.milp += temp[n][e][t] >= \
                                     self.tempSet[n][e] - self.bigNumber[n][e] * (1 - binAux[n][e][t]), \
                            f'Constraint_8.1_{n}_{e}_{t:07d}'
                        self.milp += temp[n][e][t] <= \
                                     self.tempSet[n][e] + self.bigNumber[n][e] * binAux[n][e][t], \
                            f'Constraint_8.2_{n}_{e}_{t:07d}'
                        # if temp[n][e][t] > tempSet
                        self.milp += w_water[n][e][t] >= \
                                     self.regressor_aboveSet_m_temp[n][e] * temp[n][e][t] + \
                                     self.regressor_aboveSet_m_delta[n][e] * self.delta_use[n][e][t] + \
                                     self.regressor_aboveSet_b[n][e] - \
                                     self.bigNumber[n][e] * (1 - binAux[n][e][t]), \
                            f'Constraint_8.3_{n}_{e}_{t:07d}'
                        self.milp += w_water[n][e][t] <= \
                                     self.regressor_aboveSet_m_temp[n][e] * temp[n][e][t] + \
                                     self.regressor_aboveSet_m_delta[n][e] * self.delta_use[n][e][t] + \
                                     self.regressor_aboveSet_b[n][e] + \
                                     self.bigNumber[n][e] * (1 - binAux[n][e][t]), \
                            f'Constraint_8.4_{n}_{e}_{t:07d}'
                        # else
                        self.milp += w_water[n][e][t] >= \
                                     self.regressor_belowSet_m_temp[n][e] * temp[n][e][t] + \
                                     self.regressor_belowSet_m_delta[n][e] * self.delta_use[n][e][t] + \
                                     self.regressor_belowSet_b[n][e] - \
                                     self.bigNumber[n][e] * binAux[n][e][t], \
                            f'Constraint_8.5_{n}_{e}_{t:07d}'
                        self.milp += w_water[n][e][t] <= \
                                     self.regressor_belowSet_m_temp[n][e] * temp[n][e][t] + \
                                     self.regressor_belowSet_m_delta[n][e] * self.delta_use[n][e][t] + \
                                     self.regressor_belowSet_b[n][e] + \
                                     self.bigNumber[n][e] * binAux[n][e][t], \
                            f'Constraint_8.6_{n}_{e}_{t:07d}'
                    else:
                        self.milp += w_water[n][e][t] == \
                                     temp[n][e][t] * self.ewh_capacity[n][e] * self.waterHeatCap[n][e] / 3600 * \
                                     self.delta_t[n][e] * 60, \
                            f'Constraint_8.7_{n}_{e}_{t:07d}'
        # HVAC Constraints
        if self.set_hvac is not None:
            for n, t in itertools.product(self.set_meters, self.time_series):
                for h in self.set_hvac[n]:
                    increment = f'{n}_{h}_t{t:03d}'

                    # Temperature Evolution Equation
                    if t == 0:
                        self.milp += hvac_temp[n][h][t] == self.hvac_init_temp[n][h], f'HVAC_Start_Temp_' + increment

                    if self.type[n][h] == 'inverter':
                        if t != 0:
                            # Heating equation
                            self.milp += (
                                    hvac_temp[n][h][t]
                                    - hvac_temp[n][h][t - 1]
                                    - self.mu[n][h] * (self.T_out[n][h][t] - hvac_temp[n][h][t - 1])
                                    - self.psi[n][h] * hvac_power[n][h][t] * self._delta_t
                                    <= self._big_m * (1 - hvac_mode[n][h][t])
                            ), f'HVAC_Heating_UB_' + increment
                            self.milp += (
                                    hvac_temp[n][h][t]
                                    - hvac_temp[n][h][t - 1]
                                    - self.mu[n][h] * (self.T_out[n][h][t] - hvac_temp[n][h][t - 1])
                                    - self.psi[n][h] * hvac_power[n][h][t] * self._delta_t
                                    >= -self._big_m * (1 - hvac_mode[n][h][t])
                            ), f'HVAC_Heating_LB_' + increment

                            # Cooling equation
                            self.milp += (
                                    hvac_temp[n][h][t]
                                    - hvac_temp[n][h][t - 1]
                                    - self.mu[n][h] * (self.T_out[n][h][t] - hvac_temp[n][h][t - 1])
                                    + self.psi[n][h] * hvac_power[n][h][t] * self._delta_t
                                    <= self._big_m * hvac_mode[n][h][t]
                            ), f'HVAC_Cooling_UB_' + increment
                            self.milp += (
                                    hvac_temp[n][h][t]
                                    - hvac_temp[n][h][t - 1]
                                    - self.mu[n][h] * (self.T_out[n][h][t] - hvac_temp[n][h][t - 1])
                                    + self.psi[n][h] * hvac_power[n][h][t] * self._delta_t
                                    >= -self._big_m * hvac_mode[n][h][t]
                            ), f'HVAC_Cooling_LB_' + increment

                        self.milp += delta_hvac[n][h][t] <= 5, f'HVAC_Activation_Control_' + increment
                        self.milp += hvac_power[n][h][t] == 0.2 * delta_hvac[n][h][t] * self.hvac_capacity[n][
                            h], f'HVAC_Power_Level_' + increment

                    if self.type[n][h] == 'state':
                        if t != 0:
                            self.milp += (hvac_mode_heat[n][h][t] + hvac_mode_off[n][h][t] + hvac_mode_cool[n][h][
                                t] == 1), f'HVAC_mode_sum_' + increment
                            # Heating mode
                            self.milp += (hvac_temp[n][h][t] <= (
                                    self.T_out[n][h][t] + hvac_power[n][h][t] * self.thermal_resist[n][h] - (
                                    self.T_out[n][h][t] + hvac_power[n][h][t] * self.thermal_resist[n][h] -
                                    hvac_temp[n][h][t - 1]) * math.exp(
                                - self._delta_t / (self.thermal_resist[n][h] * self.thermal_cap[n][h])))
                                          + self._big_m * (1 - hvac_mode_heat[n][h][
                                        t])), f'HVAC_Heating_UB_state' + increment
                            self.milp += (hvac_temp[n][h][t] >= (
                                    self.T_out[n][h][t] + hvac_power[n][h][t] * self.thermal_resist[n][h] - (
                                    self.T_out[n][h][t] + hvac_power[n][h][t] * self.thermal_resist[n][h] -
                                    hvac_temp[n][h][t - 1]) * math.exp(
                                - self._delta_t / (self.thermal_resist[n][h] * self.thermal_cap[n][h])))
                                          - self._big_m * (1 - hvac_mode_heat[n][h][
                                        t])), f'HVAC_Heating_LB_state' + increment

                            # off mode
                            self.milp += (hvac_temp[n][h][t] <= (
                                    self.T_out[n][h][t] - (
                                    self.T_out[n][h][t] -
                                    hvac_temp[n][h][t - 1]) * math.exp(
                                - self._delta_t / (self.thermal_resist[n][h] * self.thermal_cap[n][h])))
                                          + self._big_m * (
                                                  1 - hvac_mode_off[n][h][t])), f'HVAC_Off_UB_state' + increment
                            self.milp += (hvac_temp[n][h][t] >= (
                                    self.T_out[n][h][t] - (
                                    self.T_out[n][h][t] -
                                    hvac_temp[n][h][t - 1]) * math.exp(
                                - self._delta_t / (self.thermal_resist[n][h] * self.thermal_cap[n][h])))
                                          - self._big_m * (
                                                  1 - hvac_mode_off[n][h][t])), f'HVAC_Off_LB_state' + increment

                            # Cooling mode
                            self.milp += (hvac_temp[n][h][t] <= (
                                    self.T_out[n][h][t] - hvac_power[n][h][t] * self.thermal_resist[n][h] - (
                                    self.T_out[n][h][t] - hvac_power[n][h][t] * self.thermal_resist[n][h] -
                                    hvac_temp[n][h][t - 1]) * math.exp(
                                - self._delta_t / (self.thermal_resist[n][h] * self.thermal_cap[n][h])))
                                          + self._big_m * (1 - hvac_mode_cool[n][h][
                                        t])), f'HVAC_Cooling_UB_state' + increment
                            self.milp += (hvac_temp[n][h][t] >= (
                                    self.T_out[n][h][t] - hvac_power[n][h][t] * self.thermal_resist[n][h] - (
                                    self.T_out[n][h][t] - hvac_power[n][h][t] * self.thermal_resist[n][h] -
                                    hvac_temp[n][h][t - 1]) * math.exp(
                                - self._delta_t / (self.thermal_resist[n][h] * self.thermal_cap[n][h])))
                                          - self._big_m * (1 - hvac_mode_cool[n][h][
                                        t])), f'HVAC_Cooling_LB_state' + increment

                        self.milp += hvac_active[n][h][t] == hvac_mode_heat[n][h][t] + hvac_mode_cool[n][h][
                            t], f'HVAC_Active_Link_' + increment
                        self.milp += hvac_power[n][h][t] == hvac_active[n][h][t] * self.hvac_capacity[n][
                            h], f'HVAC_On_Off_' + increment

                    # Force HVAC Activation If Temperature Exceeds Limits
                    # self.milp += hvac_temp[n][h][t] <= self.hvac_temp_max[n][h] + self._big_m * hvac_active[n][h][t], f'HVAC_Turn_On_Above_' + increment
                    # self.milp += hvac_temp[n][h][t] >= self.hvac_temp_min[n][h] - self._big_m * hvac_active[n][h][t], f'HVAC_Turn_On_Below_' + increment

                    self.milp += hvac_temp[n][h][t] - self.hvac_temp_max[n][h] <= hvac_cost_comfort[n][h][
                        t], f'HVAC_Cost_Above_UB' + increment
                    self.milp += hvac_temp[n][h][t] - self.hvac_temp_min[n][h] >= -hvac_cost_comfort[n][h][
                        t], f'HVAC_Cost_Below_UB' + increment

        if self.set_hp is not None:
            for n, t in itertools.product(self.set_meters, self.time_series):
                for hp in self.set_hp[n]:

                    if self.hp_type[n][hp] == 'inverter':

                        increment = f'{n}_{hp}_t{t:03d}'

                        self.milp += self.hp_power[n][hp][t] <= self.hp_power_rated[n][hp]

                        # HPT-2.1
                        self.milp += (self.hp_power[n][hp][t] >= self.heating_kwh[n][hp][t] +
                                      self.circulation_kw[n][hp][t] + self.tank_heating_kwh[n][hp][
                                          t]), f'HP_Total_Power_' + increment

                        # HPT-2.2
                        self.milp += (self.heating_kwh[n][hp][t] >= self.hp_mass_hw_demand[n][hp][t] * self.hp_c_p[n][
                            hp] * (
                                              self.hp_temp_desired[n][hp] - self.hp_temp_inlet[n][
                                          hp]) / 3600 * self._delta_t), f'HP_Heating_Demand_' + increment

                        # HPT-2.3
                        self.milp += (self.circulation_kw[n][hp][t] >= self.hp_mass_radiator[n][hp][t] * self.hp_c_p[n][
                            hp] * (
                                              self.hp_temp_outlet[n][hp][t] - self.hp_temp_return[n][hp][
                                          t]) / 3600 * self._delta_t), f'HP_Circulation_Power_' + increment

                        # HPT-2.5
                        # if t ==0:
                        # 	self.milp += (self.tank_heating_kwh[hp][t] == self.hp_capacity_tank[hp] * self.hp_c_p[hp] * self.hp_temp_out_init[hp]/3600), f'HP_Tank_Init_' + increment
                        if t != 0:
                            # HPT-2.4
                            self.milp += (self.tank_heating_kwh[n][hp][t] >= self.hp_capacity_tank[n][hp] *
                                          self.hp_c_p[n][hp] * (
                                                  self.hp_temp_outlet[n][hp][t] - self.hp_temp_outlet[n][hp][
                                              t - 1]) / 3600 * self._delta_t), f'HPT2.4_Tank_Heating_' + increment

                        # HPT-3
                        # self.milp += self.circulation_kw[hp][t] == ((self.hp_h_rad[hp] * self.hp_area_rad[hp]) * ((self.hp_temp_outlet[hp][t]
                        # 										+ self.hp_temp_return[hp][t])/2 - self.hp_temp_indoor[hp][t])), f'HP_Convective_Limit_' + increment

                        self.milp += (self.hp_mass_radiator[n][hp][t] * self.hp_c_p[n][hp] * (
                                self.hp_temp_outlet[n][hp][t] - self.hp_temp_return[n][hp][t]) / 3600) == (
                                             (self.hp_h_rad[n][hp] * self.hp_area_rad[n][hp]) * (
                                             (self.hp_temp_outlet[n][hp][t]
                                              + self.hp_temp_return[n][hp][t]) / 2 - self.hp_temp_indoor[n][hp][
                                                 t]) * self._delta_t), f'HP_Convective_Limit_' + increment

                        # HPT-4.1/ 4.2: Indoor temperature evolution
                        if t == 0:
                            self.milp += (self.hp_temp_indoor[n][hp][t] == self.hp_temp_indoor_init[n][
                                hp]), f'HP_Indoor_Init_' + increment
                            self.milp += (self.hp_temp_outlet[n][hp][t] == self.hp_temp_out_init[n][
                                hp]), f'HP_Outlet_Init_' + increment
                        else:
                            # self.milp += ( self.hp_temp_indoor[h][t] == self.hp_temp_indoor[h][t - 1]
                            # 					+ (self._delta_t / self.hp_thermal_resistance[h]) * self.hp_u_value[h] * (self.hp_t_out[h][t - 1] - self.hp_temp_indoor[h][t - 1])
                            # 					+ self.hp_h_rad[h] * self.hp_area_rad[h] * (self.hp_temp_outlet[h][t - 1] - self.hp_temp_indoor[h][t - 1])
                            # 			 ), f'HP_Indoor_Evolution_' + increment

                            self.milp += (self.hp_temp_indoor[n][hp][t] == self.hp_temp_indoor[n][hp][t - 1] *
                                          self.hp_u_value[n][hp] +
                                          self.hp_t_out[n][hp][t - 1] * (
                                                  self._delta_t / self.hp_thermal_resistance[n][hp])
                                          + self.hp_h_rad[n][hp] * self.hp_area_rad[n][hp] * self.hp_temp_outlet[n][hp][
                                              t]), f'HP_Indoor_Evolution_' + increment

                        # HPT-5
                        self.milp += (self.hp_temp_indoor[n][hp][t] + self.hp_cost_comfort[n][hp][t] >=
                                      self.hp_temp_indoor_min[n][
                                          hp]), f'HP_Temp_Min_WithSlack_' + increment
                        self.milp += (self.hp_temp_indoor[n][hp][t] + self.hp_cost_comfort[n][hp][t] <=
                                      self.hp_temp_indoor_max[n][
                                          hp]), f'HP_Temp_Max_WithSlack_' + increment
                        # HPT-5
                        # self.milp += (self.hp_temp_outlet[n][hp][t] + self.hp_cost_comfort[n][hp][t] >= self.hp_temp_out_min[n][
                        # 	hp]), f'HP_TempOut_Min_WithSlack_' + increment
                        # self.milp += (self.hp_temp_outlet[n][hp][t] + self.hp_cost_comfort[n][hp][t] <= self.hp_temp_out_max[n][
                        # 	hp]), f'HP_TempOut_Max_WithSlack_' + increment

        if self.sets_hydrogen_storage is not None:

            for n, t in itertools.product(self.set_meters, self.time_series):
                for tank in self.sets_hydrogen_storage[n]:
                    increment_tank = f"{n}_{tank}_t{t:05d}"

                    # --- Hydrogen balance ---
                    # sum of all ECs linked to this tank
                    ec_terms = [m_h2[n][ec][t] for ec in tank_links[n][tank]["EC"]]
                    # sum of all FCs linked to this tank
                    fc_terms = [m_fc[n][fc][t] for fc in tank_links[n][tank]["FC"]]

                    # Net update to tank storage
                    h2_update = lpSum(ec_terms) - lpSum(fc_terms) - m_chp[n][tank][t]

                    # Hydrogen tank dynamics
                    if t == 0:
                        self.milp += (
                            h2_storage[n][tank][0] == self._init_h2[n][tank] + h2_update,
                            "H2_storage_update_t0_" + increment_tank,
                        )
                    else:
                        self.milp += (
                            h2_storage[n][tank][t] == h2_storage[n][tank][t - 1] + h2_update,
                            "H2_storage_update_" + increment_tank,
                        )

                    # Tank capacity limits
                    self.milp += (
                        h2_storage[n][tank][t] <= self._h2_capacity[n][tank],
                        "H2_maximum_storage_" + increment_tank,
                    )
                    self.milp += (
                        h2_storage[n][tank][t] >= self._h2_min[n][tank],
                        "H2_withdrawal_condition_" + increment_tank,
                    )

                    # --- Electrolyzer constraints ---
                    for ec in tank_links[n][tank]["EC"]:
                        increment_ec = f"{n}_{ec}_t{t:05d}"
                        if self._variable_eff_ec:
                            segments = self._eff_ec[n][ec] # Unpacking slopes and intercepts
                            n_segments = len(self._eff_ec[n][ec])

                            # Hydrogen production
                            self.milp += (
                                m_h2[n][ec][t] == lpSum(
                                    e_ec_s[n][ec][f"s{s + 1}"][t] * self._delta_t * segments[s][0] +
                                    segments[s][1] * b_ec_s[n][ec][f"s{s + 1}"][t]
                                    for s in range(n_segments)
                                ),
                                "H2_production_EC_variable_" + increment_ec,
                            )

                            self.milp += (
                                lpSum(b_ec_s[n][ec][f"s{s + 1}"][t] for s in range(n_segments)) == delta_ec_on[n][ec][t],
                                "Segment_activation_" + increment_ec
                            )

                            self.milp += (
                                lpSum(e_ec_s[n][ec][f"s{s + 1}"][t] for s in range(n_segments)) == e_ec_total[n][ec][t],
                                "Energy_per_segment_" + increment_ec
                            )

                            for s in range(n_segments):

                                self.milp += (
                                    self._power_bounds_ec[n][ec][s] * b_ec_s[n][ec][f"s{s + 1}"][t] <= e_ec_s[n][ec][f"s{s + 1}"][t],
                                    f"Lower_limit_segment_{s}_{t}" + increment_ec
                                )

                                self.milp += (
                                    e_ec_s[n][ec][f"s{s + 1}"][t] <= self._power_bounds_ec[n][ec][s + 1] * b_ec_s[n][ec][f"s{s + 1}"][t],
                                    f"Upper_limit_segment_{s}_{t}" + increment_ec
                                )

                        else:
                            self.milp += (
                                m_h2[n][ec][t] == e_ec_total[n][ec][t] * self._eff_ec[n][ec] / self._hhv
                            )

                        self.milp += (
                            e_ec_total[n][ec][t] <= self._pn[n][ec] * self._delta_t * delta_ec_on[n][ec][t],
                            "H2_max_input_" + increment_ec,
                        )
                        self.milp += (
                            e_ec_total[n][ec][t] >= self._pmin_ec[n][ec] * self._delta_t * delta_ec_on[n][ec][t],
                            "H2_min_input_" + increment_ec,
                        )
                        # CHP demand constraints
                        if self._chp_demand:
                            self.milp += (
                                m_chp[n][tank][t] <= self._chp_demand[t % 24] * (1 - delta_ec_on[n][ec][t]),
                                "CHP_production_" + increment_tank,
                            )

                    # --- Fuel cell constraints ---
                    for fc in tank_links[n][tank]["FC"]:
                        increment_fc = f"{n}_{fc}_t{t:05d}"
                        if self._variable_eff_fc:
                            segments = self._eff_fc[n][fc]  # Unpacking slopes and intercepts
                            n_segments = len(self._eff_fc[n][fc])

                            # Hydrogen production
                            self.milp += (
                                m_fc[n][fc][t] == lpSum(
                                    e_fc_s[n][fc][f"s{s + 1}"][t] * segments[s][0] + segments[s][1] *
                                    b_fc_s[n][fc][f"s{s + 1}"][t] for s in range(n_segments)),
                                "H2_production_FC_variable_" + increment_fc,
                            )

                            self.milp += (
                                lpSum(b_fc_s[n][fc][f"s{s + 1}"][t] for s in range(n_segments)) == delta_fc_on[n][fc][
                                    t],
                                "Segment_activation_" + increment_fc
                            )

                            self.milp += (
                                lpSum(e_fc_s[n][fc][f"s{s + 1}"][t] for s in range(n_segments)) == e_fc_total[n][fc][t],
                                "Energy_per_segment_" + increment_fc
                            )

                            for s in range(n_segments - 1):
                                self.milp += (
                                    self._power_bounds_fc[n][fc][s] * b_fc_s[n][fc][f"s{s + 1}"][t] <=
                                    e_fc_s[n][fc][f"s{s + 1}"][t],
                                    "Lower_limit_segment_" + increment_fc
                                )

                                self.milp += (
                                    e_fc_s[n][fc][f"s{s + 1}"][t] <= self._power_bounds_fc[n][fc][s + 1] *
                                    b_fc_s[n][fc][f"s{s + 1}"][t],
                                    "Upper_limit_segment_" + increment_fc
                                )
                        else:
                            self.milp += (
                                e_fc_total[n][fc][t] == m_fc[n][fc][t] * self._eff_fc[n][fc] * self._hhv,
                                "Fuel_cell_output_" + increment_fc,
                            )
                        self.milp += (
                            e_fc_total[n][fc][t] >= self._pmin_fc[n][fc] * delta_fc_on[n][fc][t] * self._delta_t,
                            "Fuel_cell_upper_limit_" + increment_fc,
                        )
                        self.milp += (
                            e_fc_total[n][fc][t] <= self._pn_fc[n][fc] * delta_fc_on[n][fc][t] * self._delta_t,
                            "Fuel_cell_lower_limit_" + increment_fc,
                        )

                    # --- Exclusivity: no EC and FC at same time ---
                    for ec in tank_links[n][tank]["EC"]:
                        for fc in tank_links[n][tank]["FC"]:
                            self.milp += (
                                delta_ec_on[n][ec][t] + delta_fc_on[n][fc][t] <= 1,
                                f"Conversion_production_exclusive_{n}_{tank}_{t:05d}_{ec}_{fc}",
                            )

        for n in self.set_meters:
            increment = f'{n}'

            # Eq. 19
            self.milp += lpSum(
                e_sup_retail[n][t] * self._l_buy[n][t] - e_sur_retail[n][t] * self._l_sell[n][t]
                + e_sup_market[n][t] * self._l_market_buy[t] - e_sur_market[n][t] * self._l_market_sell[t]
                + e_slc[n][t] * self._l_grid[t]
                + p_extra[n][t] * self._l_extra
                + lpSum(self._deg_cost[n][b] * e_bd[n][b][t] for b in self.sets_btm_storage[n])
                + (e_pur[n][t] - e_sale[n][t]) * self._l_lem[t]
                for t in self.time_series
            ) <= round_up(self._c_ind[n]), 'Stage_1_cost_' + increment

        # Write MILP to .lp file
        dir_name = os.path.abspath(os.path.join(__file__, '..'))
        lp_file = os.path.join(dir_name, f'Stage2Pool.lp')
        self.milp.writeLP(lp_file)

        # Set the solver to be called
        if self.solver == 'CBC' and 'PULP_CBC_CMD' in listSolvers(onlyAvailable=True):
            self.milp.setSolver(pulp.PULP_CBC_CMD(msg=False, timeLimit=self.timeout, gapRel=self.mipgap))

        elif self.solver == 'GUROBI' and 'GUROBI_CMD' in listSolvers(onlyAvailable=True):
            self.milp.setSolver(GUROBI_CMD(msg=False, timeLimit=self.timeout, mip=self.mipgap))

        elif self.solver == 'CPLEX' and 'CPLEX_CMD' in listSolvers(onlyAvailable=True):
            self.milp.setSolver(CPLEX_CMD(msg=False, timeLimit=self.timeout, gapRel=self.mipgap))

        elif self.solver == 'HiGHS' and 'HiGHS_CMD' in listSolvers(onlyAvailable=True):
            self.milp.setSolver(HiGHS_CMD(msg=False, timeLimit=self.timeout, gapRel=self.mipgap, threads=1))

        else:
            raise ValueError(f'{self.solver}_CMD not available in puLP; '
                             f'please install the required solver or try a different one')

        logger.debug('-- defining the collective (pool) MILP problem... DONE!')

        return

    def solve_milp(self):
        """
        Function that heads the definition and solution of the second stage MILP.
        """
        # Define the MILP
        self.__define_milp()

        # Solve the MILP
        logger.debug('-- solving the collective (pool) MILP problem...')

        try:
            self.milp.solve()
            status = LpStatus[self.milp.status]
            opt_value = value(self.milp.objective)

        except Exception as e:
            logger.warning(f'Solver raised an error: \'{e}\'. Considering problem as "Infeasible".')
            status = 'Infeasible'
            opt_value = None

        self.status = status
        self.obj_value = opt_value

        logger.debug('-- solving the collective (pool) MILP problem... DONE!')

        return

    def generate_outputs(self) -> OutputsS2PoolDict:
        """
        Function for generating the outputs of optimization, namely the battery's set points
        and other MILP results.
        :return: outputs dictionary with MILP variables' and other computed values
        """
        logger.debug('-- generating outputs from the collective (pool) MILP problem...')

        # Return empty if optimization failed
        if self.obj_value is None:
            return {}

        # Core always-present outputs
        outputs = {
            "obj_value": self.obj_value,
            "milp_status": self.status,
        }

        # Always include these base components
        outputs.update({
            "e_sup_retail": {}, "e_sur_retail": {},
            "e_sup_market": {}, "e_sur_market": {},
            "delta_sup": {}, "e_pur_pool": {},
            "e_sale_pool": {}, "e_cmet": {},
            "e_slc_pool": {}, "e_consumed": {},
            "e_alc": {}, "delta_slc": {},
            "delta_cmet": {}, "delta_alc": {},
            "p_extra": {},
        })

        # Optional flags
        if self.strict_pos_coeffs:
            outputs["delta_coeff"] = {}
        if self.total_share_coeffs:
            outputs["delta_rec_balance"] = {'scalar': []}  # scalar list
            outputs["delta_meter_balance"] = {}

        # BTM storage
        if any(self._meters_data[n].get('btm_storage') for n in self.set_meters):
            outputs.update({
                "e_bat": {}, "soc_bat": {},
                "e_bc": {}, "e_bd": {},
                "delta_bc": {},
            })

        # EVs
        if any(self._meters_data[n].get('btm_evs') for n in self.set_meters):
            outputs.update({
                "ev_stored": {}, "p_ev_charge": {}, "p_ev_discharge": {},
            })

        # EWH
        if self._ewh_dataset:
            outputs.update({
                "ewh_temp": {}, "ewh_delta_in": {},
                "ewh_optimized_load": {}, "ewh_original_load": {},
                "ewh_delta_use": {},
            })

        # HVAC
        if any(self.set_hvac.values()):
            outputs.update({
                "hvac_power": {}, "hvac_temp": {}, "hvac_cost_comfort": {},
            })

        # Heat pumps
        if any(self.set_hp.values()):
            outputs.update({
                "hp_power": {}, "hp_temp_indoor": {}, "hp_power_circulation": {},
                "hp_power_heating": {}, "hp_power_tank": {}, "hp_outlet_temp": {},
            })

        # P2H: electrolyzers + storage + fuel cells
        if any(self.sets_electrolyzer.values()) or any(self.sets_hydrogen_storage.values()) or any(self.sets_fuel_cell.values()):
            outputs.update({
                "e_ec_total": {}, "h2_storage": {}, "m_chp": {}, "e_fc_total": {}, "m_fc": {}, "m_h2": {}
            })

        # Prepare prefix list for variable name matching
        output_keys = sorted(list(outputs.keys()), key=len, reverse=True)

        # Parse MILP variables into structured dicts/lists
        for v in self.milp.variables():
            if "dummy" in v.name:
                continue
            name, val = v.name, v.varValue
            matches = next((sub for sub in output_keys if name.startswith(sub + "_")), None)
            if matches is None:
                continue

            components = name.replace(matches + "_", "").strip("_").split("_")
            match len(components):
                # Only time index
                case 1:
                    if components[0].startswith("t"):
                        outputs[matches].setdefault("scalar", []).append(val)
                    else:
                        outputs[matches][components[0]] = val

                # Meter + time
                case 2:
                    meter_id, _ = components
                    outputs[matches].setdefault(meter_id, []).append(val)

                # Meter + DER/EV + time
                case 3:
                    meter_id, der_id, _ = components
                    outputs[matches].setdefault(meter_id, {}).setdefault(der_id, []).append(val)

                case _:
                    continue

        # Add Stage 2 costs
        outputs['c_ind2pool'] = {n: None for n in self.set_meters}
        outputs['deg_cost2pool'] = {n: None for n in self.set_meters}
        outputs['p_extra_cost2pool'] = {n: None for n in self.set_meters}
        outputs['c_ind2pool_without_deg'] = {n: None for n in self.set_meters}
        outputs['c_ind2pool_without_p_extra'] = {n: None for n in self.set_meters}
        outputs['c_ind2pool_without_deg_and_p_extra'] = {n: None for n in self.set_meters}

        rematchd = {key.replace('-', '_'): key for key in self.set_meters}
        constraints = [self.milp.constraints[c] for c in self.milp.constraints if c.startswith('Stage_1_cost_')]

        for constraint in constraints:
            n = rematchd[constraint.name.split('Stage_1_cost_')[-1]]

            # p_extra cost
            p_extra = sum(outputs['p_extra'][n])
            p_extra_cost = p_extra * self._l_extra
            outputs['p_extra_cost2pool'][n] = p_extra_cost

            # degradation cost
            deg_cost = sum(self._deg_cost[n][b] * outputs['e_bd'][n][b][t]
                           for b in self.sets_btm_storage[n] for t in self.time_series)
            outputs['deg_cost2pool'][n] = deg_cost

            # stage cost
            constraint_sum = sum(var.varValue * coefficient for var, coefficient in constraint.items())
            constraint_sum += constraint.constant + self._c_ind[n]
            outputs['c_ind2pool'][n] = round(constraint_sum, 3)

            outputs['c_ind2pool_without_deg'][n] = outputs['c_ind2pool'][n] - deg_cost
            outputs['c_ind2pool_without_p_extra'][n] = outputs['c_ind2pool'][n] - p_extra_cost
            outputs['c_ind2pool_without_deg_and_p_extra'][n] = outputs['c_ind2pool'][n] - deg_cost - p_extra_cost

        # Market equilibrium dual prices
        dual_prices = [abs(self.milp.constraints[c].pi)
                       for c in self.milp.constraints if c.startswith('Market_equilibrium_')]
        outputs['dual_prices'] = [round(dp, 4) for dp in dual_prices]

        logger.debug('-- generating outputs from the collective (pool) MILP problem... DONE!')
        return outputs
