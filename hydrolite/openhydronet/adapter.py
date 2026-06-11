from __future__ import annotations

from typing import Any


def describe_openhydronet_adapter() -> dict[str, str]:
    return {
        "status": "placeholder",
        "purpose": "Map HydroLite, GEE, and observed gauge data into a future OpenHydroNet-style schema.",
    }


def map_hydrolite_to_openhydronet_schema_placeholder(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    return {
        "status": "placeholder",
        "message": "HydroLite result_flow.csv to OpenHydroNet feature mapping is not implemented yet.",
    }


def map_gee_to_openhydronet_schema_placeholder(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    return {
        "status": "placeholder",
        "message": "GEE static and meteorological features to OpenHydroNet schema mapping is not implemented yet.",
    }
