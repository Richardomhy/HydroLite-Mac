import json
import hashlib

import pandas as pd
import yaml

from hydrolite.gamma_lag_features import build_gamma_kernel, convolve_causal_series
from hydrolite.gamma_validation import DEMO_KINDS, generate_synthetic_demo_data, response_metrics, run_multi_truth, run_single_truth


def test_synthetic_demo_manifest_and_required_files(tmp_path):
    outputs = generate_synthetic_demo_data(tmp_path)
    required = {"rainfall.csv", "effective_rainfall.csv", "observed_response.csv", "truth_parameters.yaml", "gamma_config.yaml", "generation_manifest.json", "expected_results.json"}
    assert set(outputs) == set(DEMO_KINDS)
    for folder in outputs.values():
        assert required <= {path.name for path in folder.iterdir()}
        manifest = json.loads((folder / "generation_manifest.json").read_text(encoding="utf-8"))
        assert manifest["synthetic_demo"] is True and manifest["checksums"]
        for name, expected in manifest["checksums"].items():
            assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected


def test_single_multi_noise_and_forward_consistency(tmp_path):
    single = run_single_truth(tmp_path); multi = run_multi_truth(tmp_path)
    assert single["status"] == "passed" and multi["status"] == "passed"
    assert single["metrics"]["NSE"] >= .999 and single["metrics"]["KGE"] >= .995 and abs(single["metrics"]["PBIAS"]) <= .1
    assert abs(single["metrics"]["full_convolution_volume_error"]) <= 1e-10
    assert multi["metrics"]["NSE"] >= .999 and multi["metrics"]["component_sum_max_error"] <= 1e-12
    assert single["noisy_metrics"]["NSE"] > .95


def test_stress_demo_preserves_forward_consistency(tmp_path):
    folder = generate_synthetic_demo_data(tmp_path)["stress_test"]
    source = pd.read_csv(folder / "effective_rainfall.csv")["effective_rainfall"].to_numpy()
    observed = pd.read_csv(folder / "observed_response.csv")["clean_response"].to_numpy()
    truth = yaml.safe_load((folder / "truth_parameters.yaml").read_text(encoding="utf-8"))["single"]
    predicted = convolve_causal_series(source, build_gamma_kernel(truth["shape"], truth["scale"], truth["support_length"], 1.0)) * truth["runoff_coefficient"]
    assert response_metrics(observed, predicted)["NSE"] >= .999
