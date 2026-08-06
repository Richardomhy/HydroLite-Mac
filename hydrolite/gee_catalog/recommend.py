from __future__ import annotations

from hydrolite.gee_catalog.loader import load_catalog

_USES = {"continuous_hydrology": ["precipitation", "dem", "soil moisture"], "drought_forecast": ["precipitation", "soil moisture", "surface water"], "flood_susceptibility": ["dem", "land cover", "precipitation"]}


def recommend_datasets(model_id: str, config: str | None = None) -> dict:
    needs = _USES.get(model_id, ["precipitation", "dem"])
    rows = [row for row in load_catalog() if any(item in " ".join(row.get("hydrolite_use_cases", [])).lower() for item in needs)]
    return {"status": "passed", "model_id": model_id, "config": config, "needs": needs, "recommendations": rows}
