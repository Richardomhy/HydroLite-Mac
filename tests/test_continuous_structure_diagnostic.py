from hydrolite.continuous_structure_diagnostic import diagnose_structural_mismatch

def test_structural_mismatch_after_truth_passes():
    assert diagnose_structural_mismatch({"simulated_to_observed_volume_ratio":.1},"passed")["status"]=="structural_mismatch"
