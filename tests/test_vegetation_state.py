from hydrolite.vegetation_state import calculate_ndvi_vegetation_factor, calculate_seasonal_vegetation_factor, validate_vegetation_factor


def test_vegetation_factors_are_bounded():
    assert validate_vegetation_factor(calculate_seasonal_vegetation_factor("2020-07-01"))["status"]=="passed"
    assert calculate_ndvi_vegetation_factor(0.8,{"slope":1.2,"intercept":0.2,"maximum":1.1})==1.1
