from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from hydrolite.gamma_lag_features import (
    build_gamma_features_from_hydrolite,
    build_gamma_kernel,
    build_multi_gamma_features,
    calculate_discrete_kernel_mean_lag,
    calculate_discrete_kernel_peak_lag,
    calculate_gamma_mean_lag,
    calculate_gamma_peak_lag,
    gamma_pdf,
    normalize_gamma_kernel,
    validate_gamma_kernel,
)


def test_gamma_math_parameters_normalization_and_lags():
    density = gamma_pdf([0, 1, 2], 2.5, 2.0)
    assert np.all(np.isfinite(density)) and np.all(density >= 0)
    with pytest.raises(ValueError): gamma_pdf([1], 0, 2)
    with pytest.raises(ValueError): gamma_pdf([1], 2, -1)
    kernel = build_gamma_kernel(2.5, 2.0, 40, 1.0)
    assert validate_gamma_kernel(kernel)["status"] == "passed"
    assert np.isclose(kernel.sum(), 1.0) and np.all(kernel >= 0)
    assert calculate_gamma_mean_lag(2.5, 2.0) == 5.0
    assert calculate_gamma_peak_lag(2.5, 2.0) == 3.0
    assert 4.0 < calculate_discrete_kernel_mean_lag(kernel) < 5.1
    assert calculate_discrete_kernel_peak_lag(kernel) == 3.0
    with pytest.raises(ValueError): normalize_gamma_kernel([1, -1])


def test_multi_components_and_hydrolite_adapter_preserve_ledger():
    components = [
        {"component_id": "quick", "shape": 1.5, "scale": 1, "support_length": 8, "weight": 2, "enabled": True},
        {"component_id": "slow", "shape": 4, "scale": 2, "support_length": 20, "weight": 1, "enabled": True},
    ]
    source = np.r_[1.0, np.zeros(29)]
    result = build_multi_gamma_features(source, components)
    assert np.allclose(result["features"].to_numpy() @ result["normalized_weights"], result["combined"])
    assert result["raw_weights"] == [2.0, 1.0] and np.isclose(sum(result["normalized_weights"]), 1)
    frame = pd.DataFrame({"effective_rainfall": source, "physical_runoff": source * .2})
    adapted = build_gamma_features_from_hydrolite(frame, {"source_variable": "effective_rainfall", "components": components, "source_unit": "mm"})
    assert adapted["provenance"]["derived_feature_only"] is True
    assert adapted["provenance"]["physical_water_balance_modified"] is False
    assert np.array_equal(adapted["feature_frame"]["physical_runoff"], frame["physical_runoff"])


def test_no_neural_or_sklearn_dependency_in_gamma_core():
    root = Path(__file__).resolve().parents[1]
    text = "\n".join((root / "hydrolite" / name).read_text(encoding="utf-8") for name in ("gamma_lag_features.py", "gamma_validation.py", "gamma_benchmark.py"))
    assert "import sklearn" not in text and "import torch" not in text and "tensorflow" not in text


def test_gamma_cli_status_smoke():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run([sys.executable, "-m", "hydrolite", "gamma", "status"], cwd=root, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert '"sklearn_required": false' in completed.stdout
