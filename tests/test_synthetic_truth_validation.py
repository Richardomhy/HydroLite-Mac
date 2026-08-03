from hydrolite.synthetic_truth_validation import generate_synthetic_truth, run_truth_forward_validation

def test_truth_forward_recovery(tmp_path):
    generate_synthetic_truth(tmp_path)
    assert run_truth_forward_validation(tmp_path)["status"]=="passed"
