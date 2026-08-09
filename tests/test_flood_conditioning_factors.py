import pandas as pd

from hydrolite.flood_susceptibility_features import detect_constant_factors, detect_high_correlation, detect_missing_factors, validate_factor_coverage


def test_factor_qc_flags_missing_constant_and_high_correlation_without_dropping():
    frame = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8], "constant": [1, 1, 1, 1]})
    assert detect_missing_factors(frame, ["a", "missing"]).set_index("factor_id").loc["missing", "missing_fraction"] == 1
    assert detect_constant_factors(frame, ["constant"]).iloc[0].constant
    high = detect_high_correlation(frame, .8, ["a", "b"])
    assert high.iloc[0].action == "flag_only_not_auto_drop"
    assert validate_factor_coverage(frame, ["a", "missing"])["status"] == "failed"
