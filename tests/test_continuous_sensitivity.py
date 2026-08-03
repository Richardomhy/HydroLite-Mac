from hydrolite.continuous_sensitivity import generate_lhs_parameter_samples

def test_lhs_is_reproducible():
    assert generate_lhs_parameter_samples({"a":(0,1)},3,42).equals(generate_lhs_parameter_samples({"a":(0,1)},3,42))
