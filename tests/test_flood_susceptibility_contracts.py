import pandas as pd

from hydrolite.flood_susceptibility_contracts import (
    FloodConditioningFactorSpec,
    FloodInventoryPoint,
    validate_factor_spec,
)


def test_contracts_preserve_provenance_and_factor_metadata():
    point = FloodInventoryPoint("P1", "E1", pd.Timestamp("2024-01-01"), 1, 113.1, 22.5, "observed_flood", "verified", "survey", "high", {"file": "inventory.csv"})
    assert point.as_dict()["provenance"]["file"] == "inventory.csv"
    spec = FloodConditioningFactorSpec("slope", "degree", "DEM", "30m", "static", False, "terrain", "checked", {"clean_room": True})
    assert validate_factor_spec(spec)["status"] == "passed"
