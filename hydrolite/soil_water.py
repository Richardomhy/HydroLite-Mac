from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


DEMO_SOIL_PARAMETERS = {
    "soil_depth_mm": 1000.0,
    "field_capacity": 0.30,
    "wilting_point": 0.12,
    "saturation": 0.45,
    "saturated_hydraulic_conductivity": 45.0,
    "percolation_coefficient": 0.03,
    "interflow_coefficient": 0.02,
    "root_depth_mm": 600.0,
    "initial_soil_moisture": 0.27,
    "parameter_source": "synthetic_demo_default",
}


def load_soil_parameters(data: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(data, dict):
        parameters = dict(data)
    else:
        path = Path(data)
        parameters = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix.lower() in {".yaml", ".yml"} else pd.read_csv(path).iloc[0].to_dict()
    return {**DEMO_SOIL_PARAMETERS, **(parameters or {})}


def validate_soil_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    required = set(DEMO_SOIL_PARAMETERS) - {"parameter_source"}
    missing = sorted(required - set(parameters))
    errors: list[str] = []
    numeric = {}
    for key in required - set(missing):
        try:
            numeric[key] = float(parameters[key])
        except (TypeError, ValueError):
            errors.append(f"{key} must be numeric")
    if not errors and not missing:
        if not numeric["wilting_point"] < numeric["field_capacity"] < numeric["saturation"]:
            errors.append("wilting_point < field_capacity < saturation is required")
        for key in ("soil_depth_mm", "saturated_hydraulic_conductivity", "root_depth_mm"):
            if numeric[key] <= 0:
                errors.append(f"{key} must be > 0")
        for key in ("percolation_coefficient", "interflow_coefficient", "initial_soil_moisture"):
            if not 0 <= numeric[key] <= 1:
                errors.append(f"{key} must be between 0 and 1")
    return {"status": "passed" if not missing and not errors else "failed", "missing": missing, "errors": errors}


def initialize_soil_state(parameters: dict[str, Any], observations: dict[str, float] | None = None) -> dict[str, float]:
    check = validate_soil_parameters(parameters)
    if check["status"] != "passed":
        raise ValueError(f"Invalid soil parameters: {check['missing'] + check['errors']}")
    moisture = float((observations or {}).get("soil_moisture", parameters["initial_soil_moisture"]))
    moisture = float(np.clip(moisture, parameters["wilting_point"], parameters["saturation"]))
    upper_depth = min(float(parameters["root_depth_mm"]), float(parameters["soil_depth_mm"]))
    lower_depth = max(float(parameters["soil_depth_mm"]) - upper_depth, 0.0)
    return {
        "upper_soil_storage_mm": moisture * upper_depth,
        "lower_soil_storage_mm": moisture * lower_depth,
    }


def _capacities(parameters: dict[str, Any]) -> tuple[float, float]:
    upper_depth = min(float(parameters["root_depth_mm"]), float(parameters["soil_depth_mm"]))
    lower_depth = max(float(parameters["soil_depth_mm"]) - upper_depth, 0.0)
    return float(parameters["saturation"]) * upper_depth, float(parameters["saturation"]) * lower_depth


def calculate_infiltration(precipitation: float, state: dict[str, float], parameters: dict[str, Any]) -> float:
    upper_capacity, _ = _capacities(parameters)
    available_capacity = max(upper_capacity - float(state["upper_soil_storage_mm"]), 0.0)
    return float(min(max(precipitation, 0.0), available_capacity, float(parameters["saturated_hydraulic_conductivity"])))


def calculate_soil_evaporation(pet: float, state: dict[str, float], parameters: dict[str, Any]) -> float:
    upper = max(float(state["upper_soil_storage_mm"]), 0.0)
    upper_capacity, _ = _capacities(parameters)
    return float(min(max(pet, 0.0) * min(upper / max(upper_capacity, 1e-9), 1.0) * 0.35, upper))


def calculate_transpiration(pet: float, state: dict[str, float], vegetation: float | dict[str, Any]) -> float:
    upper = max(float(state["upper_soil_storage_mm"]), 0.0)
    lower = max(float(state["lower_soil_storage_mm"]), 0.0)
    factor = float(vegetation.get("factor", 1.0) if isinstance(vegetation, dict) else vegetation)
    return float(min(max(pet, 0.0) * max(factor, 0.0) * 0.65, upper + lower))


def calculate_percolation(state: dict[str, float], parameters: dict[str, Any]) -> float:
    upper_capacity, lower_capacity = _capacities(parameters)
    field_storage = float(parameters["field_capacity"]) / float(parameters["saturation"]) * upper_capacity
    lower_space = max(lower_capacity - float(state["lower_soil_storage_mm"]), 0.0)
    return float(min(max(float(state["upper_soil_storage_mm"]) - field_storage, 0.0) * float(parameters["percolation_coefficient"]), lower_space))


def calculate_interflow(state: dict[str, float], parameters: dict[str, Any]) -> float:
    upper_capacity, _ = _capacities(parameters)
    field_storage = float(parameters["field_capacity"]) / float(parameters["saturation"]) * upper_capacity
    return float(min(max(float(state["upper_soil_storage_mm"]) - field_storage, 0.0) * float(parameters["interflow_coefficient"]), float(state["upper_soil_storage_mm"])))


def update_soil_water_state(state: dict[str, float], fluxes: dict[str, float]) -> dict[str, float]:
    upper = float(state["upper_soil_storage_mm"]) + float(fluxes.get("infiltration_mm", 0.0))
    evaporation = min(float(fluxes.get("soil_evaporation_mm", 0.0)), upper)
    upper -= evaporation
    transpiration = min(float(fluxes.get("transpiration_mm", 0.0)), upper + float(state["lower_soil_storage_mm"]))
    from_upper = min(transpiration, upper)
    upper -= from_upper
    lower = float(state["lower_soil_storage_mm"]) - (transpiration - from_upper)
    percolation = min(float(fluxes.get("percolation_mm", 0.0)), upper)
    upper -= percolation
    lower += percolation
    interflow = min(float(fluxes.get("interflow_mm", 0.0)), upper)
    upper -= interflow
    groundwater_recharge = min(float(fluxes.get("groundwater_recharge_mm", 0.0)), lower)
    lower -= groundwater_recharge
    return {"upper_soil_storage_mm": max(upper, 0.0), "lower_soil_storage_mm": max(lower, 0.0)}


def calculate_soil_moisture_fraction(state: dict[str, float], parameters: dict[str, Any]) -> float:
    total_capacity = float(parameters["saturation"]) * float(parameters["soil_depth_mm"])
    return float(np.clip((float(state["upper_soil_storage_mm"]) + float(state["lower_soil_storage_mm"])) / max(total_capacity, 1e-9), 0.0, 1.0))


def validate_soil_water_balance(result: dict[str, float] | pd.DataFrame, tolerance: float = 1e-6) -> dict[str, Any]:
    if isinstance(result, pd.DataFrame):
        residual = pd.to_numeric(result.get("soil_water_balance_residual_mm", pd.Series(dtype=float)), errors="coerce")
        maximum = float(residual.abs().max()) if len(residual) else 0.0
    else:
        maximum = abs(float(result.get("soil_water_balance_residual_mm", 0.0)))
    return {"status": "passed" if maximum <= tolerance else "failed", "max_abs_residual_mm": maximum, "tolerance_mm": tolerance}
