from pathlib import Path

from hydrolite.ui.components.warning_panel import EXPERIMENTAL_NOTICE, warning_payload
from hydrolite.ui.pages.flood_susceptibility import load_flood_susceptibility_ui_status


def test_experimental_and_real_data_gates_are_explicit():
    assert "真实项目独立验证" in EXPERIMENTAL_NOTICE
    assert warning_payload("REAL_DATA_VALIDATION_MISSING")["warning_code"] == "REAL_DATA_VALIDATION_MISSING"
    status = load_flood_susceptibility_ui_status(Path("output/method_inspiration/flood_susceptibility"))
    assert status["rl_suitability"] == "rl_not_justified"
    assert status["real_data_value_added"] == "not_tested"
    assert status.get("xai_importance_stability") == "unstable"
    assert status.get("complex_model_value_added") == "not_demonstrated"


def test_flood_ui_has_no_rl_run_action_and_keeps_susceptibility_risk_gate():
    source = Path("hydrolite/ui/pages/flood_susceptibility.py").read_text(encoding="utf-8")
    assert "Susceptibility ≠ Risk" in source
    assert "RL suitability：rl_not_justified" in source
    assert "运行 RL" not in source and "train_rl" not in source
