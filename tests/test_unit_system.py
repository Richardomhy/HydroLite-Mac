def test_unit_conversion_dimensions():
    from hydrolite.unit_system import convert_unit

    assert abs(convert_unit([1], "CFS", "m3/s")["normalized_value"].iloc[0] - 0.028316846592) < 1e-12
    assert convert_unit([1], "km²", "ha")["normalized_value"].iloc[0] == 100
    assert convert_unit([1], "inch", "mm")["normalized_value"].iloc[0] == 25.4
    assert convert_unit([1], "g/L", "mg/L")["normalized_value"].iloc[0] == 1000


def test_unknown_unit_is_blocked():
    from hydrolite.unit_system import convert_unit

    try:
        convert_unit([1], "mystery", "m")
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown unit was converted")
