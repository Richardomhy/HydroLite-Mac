from pathlib import Path


def test_model_and_capability_registries(tmp_path: Path):
    from hydrolite.capability_registry import get_capability, write_capability_registry
    from hydrolite.model_registry import get_model, list_models, write_model_registry_report

    required = {"model_id", "display_name_zh", "display_name_en", "domain", "model_family", "status", "input_schema", "output_schema", "version"}
    assert all(required <= set(row) for row in list_models())
    assert get_model("hydrolite_event_model")["status"] == "available"
    assert get_model("hec_hms_reservoir_model")["status"] == "blocked_gate"
    assert get_capability("flood_forecast")["status"] == "partial"
    assert get_capability("drought_forecast")["status"] == "planned"
    assert write_model_registry_report(tmp_path)["xlsx"].exists()
    assert write_capability_registry(tmp_path)["xlsx"].exists()
