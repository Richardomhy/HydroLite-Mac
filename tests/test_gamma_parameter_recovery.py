from hydrolite.gamma_validation import IDENTIFIABILITY_STATUSES, classify_identifiability, run_parameter_recovery


def test_single_and_multi_parameter_recovery(tmp_path):
    result = run_parameter_recovery(tmp_path)
    assert result["status"] == "passed"
    assert abs(result["single"]["shape"] - 2.5) / 2.5 < .05
    assert abs(result["single"]["scale"] - 2.0) / 2.0 < .05
    assert result["single_metrics"]["NSE"] >= .995 and result["multi_metrics"]["NSE"] >= .99
    assert abs(sum(item["weight"] for item in result["multi"]["components"]) - 1) < 1e-10
    assert result["identifiability"] in {"well_identified", "equifinal_good_response"}
    assert result["identifiability"] in IDENTIFIABILITY_STATUSES
    assert classify_identifiability(.999, .4) == "equifinal_good_response"
    assert classify_identifiability(.8, .1, boundary_hit=True) == "boundary_limited"
