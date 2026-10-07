import numpy as np
from scipy.interpolate import interp1d


# Function that returns the degradation curve data needed for the piecewise approximation
def get_curve_points(curve, capex, num_pts_real, num_seg_approx):
    # Definition of curve coefficients
    def calculate_curve_value(dod, capex):  # Function with the mathematical expression of the curve to be plotted
        aux_dod = 100 - dod  # invert the DOD values, from the x-axis, as required by the degradation model methodology
        a1, a2, a3, a4, a5 = curve['a1'], curve['a2'], curve['a3'], curve['a4'], curve[
            'a5']  # receive the curve coefficient values into their respective variables
        return capex / (a1 + a2 * np.exp(a3 * (aux_dod * 0.01)) + a4 * np.exp(
            a5 * (aux_dod * 0.01)))  # return the y-value (f(x)) of the degradation function for a given dod/soc

    # REAL CURVE
    # Definition of the x-axis (DOD values between 0% and 100%, based on known points)
    dod_values_real = np.linspace(0, 100,
                                  num_pts_real)  # 'numpy.ndarray' with DOD values for the 30 "known" points of the curve
    # Definition of the y-axis (degradation values as a function of DOD values defined in the previous line, according to the mathematical expression of the curve)
    curve_values_real = np.array([calculate_curve_value(dod, capex) for dod in
                                  dod_values_real])  # calculation of real curve values (numpy array)

    # APPROXIMATED CURVE (PIECEWISE)
    # Definition of the x-axis (DOD values between 0% and 100%, based on the number of line segments of the approximation)
    dod_values_approx = np.linspace(0, 100,
                                    num_seg_approx + 1)  # np array with DOD interval for the approximated curve (based on line segments)
    # Definition of the y-axis (based on interpolation)
    interp_func = interp1d(dod_values_real, curve_values_real, kind='linear')  # interpolation based on the real curve
    interp_curve_values = interp_func(dod_values_approx)  # real degradation values based on DOD

    # STORE THE FUNCTION RESULTS
    slopes = []  # Initialize an empty array to store the values of slope
    for i in range(len(dod_values_approx) - 1):  # iterate over all known points
        dod_start = dod_values_approx[i]  # starting point on the x-axis for analysis
        dod_end = dod_values_approx[i + 1]  # ending point on the y-axis for analysis
        # Find the indices of the nearest known points for this interval
        idx_start = np.abs(dod_values_real - dod_start).argmin()
        idx_end = np.abs(dod_values_real - dod_end).argmin()
        slope = (curve_values_real[idx_end] - curve_values_real[idx_start]) / (
                    dod_values_real[idx_end] - dod_values_real[idx_start])  # calculate the slope
        slopes.append(slope)  # Add the value of slope to the array

    soc_base = [percent / 100 for percent in dod_values_approx]  # Create the list 'soc_base' from 'dod_values_approx'.
    soc_min, soc_max = soc_base[:-1], soc_base[
                                      1:]  # taking all elements except the last one; taking all elements except the first

    # dictionay with data to return
    curve_data = {'cost_max': interp_curve_values[: -1],  # maximum degradation cost (y-value) of each segment
                  'cost_min': interp_curve_values[1:],  # minimum degradation cost (y-value) of each segment
                  'soc_max': soc_max,  # maximum soc limit (x-value) of segment
                  'soc_min': soc_min,  # minimum soc limit (x-value) of segment
                  'slope': [value * 100 for value in slopes],  # list of 'slopes' of each segment.
                  'nr_segments': range(num_seg_approx)  # number of segments.
                  }

    return curve_data



