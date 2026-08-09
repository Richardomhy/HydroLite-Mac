import pandas as pd

from hydrolite.flood_xai import feature_importance_stability, validate_xai_causality_claim, xai_status


def test_xai_fallback_and_causal_claim_gate():
    assert "permutation_importance" in xai_status()["fallbacks"]
    assert validate_xai_causality_claim("Feature association only, not causal effect.")["status"] == "passed"
    assert validate_xai_causality_claim("This factor causes flooding.")["status"] == "failed"


def test_importance_stability_is_reported_across_replicates():
    frame = pd.DataFrame({"factor_id": ["a", "a", "b", "b"], "importance": [.1, .3, .2, .2], "replicate": ["m1", "m2", "m1", "m2"]})
    table, summary = feature_importance_stability(frame)
    assert {"importance_mean", "importance_std"}.issubset(table)
    assert summary["status"] in {"stable", "moderately_stable", "unstable"}
