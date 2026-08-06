import numpy as np
from hydrolite.gamma_lag_features import build_causal_gamma_kernel, convolve_causal_series, validate_gamma_features


def test_gamma_kernel_is_normalized_nonnegative_and_causal():
    kernel=build_causal_gamma_kernel(2,3); result=convolve_causal_series([1,0,0],kernel)
    assert np.isclose(kernel.sum(),1) and np.all(kernel>=0) and result[0] == kernel[0] and validate_gamma_features(kernel)["causal"]
