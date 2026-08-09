from dataclasses import asdict

from hydrolite.capability_registry import get_capability
from hydrolite.water_quality_contracts import CORE_VARIABLES, WaterQualityForecastRecord, WaterQualityObservation, default_variable_specs, validate_variable_spec


def test_core_specs_use_canonical_concentration_units():
    specs = default_variable_specs()
    assert set(CORE_VARIABLES).issubset(specs)
    assert all(specs[item].canonical_unit == "mg/L" for item in CORE_VARIABLES)
    assert all(validate_variable_spec(specs[item]).status == "passed" for item in CORE_VARIABLES)


def test_observation_and_forecast_contracts_keep_provenance_fields():
    obs = WaterQualityObservation("WQ1", "2025-01-01", "TN", 1.2, reach_id="R1", source_dataset_id="lab")
    forecast = WaterQualityForecastRecord("2025-01-01", "2025-01-02", 1, "WQ1", "TN", 1.1, "mg/L", "persistence", ["local_history"], "direct", "2025-01-01", True, "validation_residual")
    assert asdict(obs)["source_dataset_id"] == "lab"
    assert asdict(forecast)["data_as_of"] == "2025-01-01"


def test_production_water_quality_remains_planned():
    assert get_capability("water_quality")["status"] == "planned"
    assert get_capability("water_quality_method_lab")["status"] == "partial"
