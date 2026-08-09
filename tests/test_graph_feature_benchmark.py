from pathlib import Path

from hydrolite.capability_registry import get_capability
from hydrolite.graph_feature_benchmark import generate_graph_demo, run_graph_trend_benchmark, validate_graph_trend_outputs


def test_graph_demo_and_benchmark_write_auditable_outputs(tmp_path):
    demo = generate_graph_demo(tmp_path / "demo"); result = run_graph_trend_benchmark(tmp_path / "output", demo["demo_dir"])
    assert result["status"] == "passed"
    assert result["real_graph_value_added"] == "not_tested"
    assert result["real_trend_value_added"] == "not_tested"
    assert (tmp_path / "output" / "reports" / "graph_trend_bundle.zip").exists()
    assert validate_graph_trend_outputs(tmp_path / "output")["status"] == "passed"


def test_m4_capabilities_are_partial_and_water_quality_remains_planned():
    for name in ("river_graph_features", "trend_aware_features", "multihorizon_forecast"):
        assert get_capability(name)["status"] == "partial"
    assert get_capability("water_quality")["status"] == "planned"


def test_core_m4_has_no_forced_sklearn_or_pytorch_import():
    root = Path(__file__).resolve().parents[1] / "hydrolite"
    text = "\n".join((root / name).read_text() for name in ("river_graph.py", "graph_hydrology_features.py", "trend_aware_features.py", "multihorizon_forecast.py", "graph_feature_benchmark.py"))
    assert "import sklearn" not in text
    assert "import torch" not in text
