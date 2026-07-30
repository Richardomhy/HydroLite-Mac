from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd


DEFAULT_GROUNDWATER_PARAMETERS = {
    "groundwater_recession_constant": 0.015,
    "baseflow_coefficient": 0.015,
    "deep_loss_coefficient": 0.001,
    "initial_groundwater_storage": 80.0,
    "groundwater_model": "linear_reservoir",
}


def initialize_groundwater_state(parameters: dict[str, Any], observations: dict[str, float] | None = None) -> dict[str, float]:
    values = {**DEFAULT_GROUNDWATER_PARAMETERS, **parameters}
    storage = float((observations or {}).get("groundwater_storage_mm", values["initial_groundwater_storage"]))
    if storage < 0:
        raise ValueError("initial groundwater storage must be non-negative")
    return {"groundwater_storage_mm": storage}


def calculate_groundwater_recharge(percolation: float, state: dict[str, float], parameters: dict[str, Any]) -> float:
    fraction = float(parameters.get("groundwater_recharge_fraction", 1.0))
    if not 0 <= fraction <= 1:
        raise ValueError("groundwater_recharge_fraction must be between 0 and 1")
    return max(float(percolation), 0.0) * fraction


def calculate_baseflow(state: dict[str, float], parameters: dict[str, Any]) -> float:
    coefficient = float(parameters.get("baseflow_coefficient", parameters.get("groundwater_recession_constant", 0.015)))
    if not 0 <= coefficient <= 1:
        raise ValueError("baseflow coefficient must be between 0 and 1 per day")
    return min(max(float(state["groundwater_storage_mm"]), 0.0) * coefficient, float(state["groundwater_storage_mm"]))


def calculate_deep_groundwater_loss(state: dict[str, float], parameters: dict[str, Any]) -> float:
    coefficient = float(parameters.get("deep_loss_coefficient", 0.0))
    if not 0 <= coefficient <= 1:
        raise ValueError("deep_loss_coefficient must be between 0 and 1 per day")
    return min(max(float(state["groundwater_storage_mm"]), 0.0) * coefficient, float(state["groundwater_storage_mm"]))


def update_groundwater_state(state: dict[str, float], fluxes: dict[str, float]) -> dict[str, float]:
    initial = max(float(state["groundwater_storage_mm"]), 0.0)
    recharge = max(float(fluxes.get("groundwater_recharge_mm", 0.0)), 0.0)
    available = initial + recharge
    baseflow = min(max(float(fluxes.get("baseflow_mm", 0.0)), 0.0), available)
    deep_loss = min(max(float(fluxes.get("deep_loss_mm", 0.0)), 0.0), available - baseflow)
    return {"groundwater_storage_mm": available - baseflow - deep_loss}


def convert_groundwater_storage_to_level(state: dict[str, float], relation: dict[str, float] | None = None) -> float | None:
    if not relation:
        return None
    return float(relation.get("intercept_m", 0.0)) + float(relation.get("slope_m_per_mm", 0.01)) * float(state["groundwater_storage_mm"])


def validate_groundwater_balance(result: dict[str, float] | pd.DataFrame, tolerance: float = 1e-6) -> dict[str, Any]:
    if isinstance(result, pd.DataFrame):
        residual = pd.to_numeric(result.get("groundwater_balance_residual_mm", pd.Series(dtype=float)), errors="coerce")
        maximum = float(residual.abs().max()) if len(residual) else 0.0
        nonnegative = bool((pd.to_numeric(result.get("groundwater_storage_mm", 0), errors="coerce") >= -tolerance).all())
    else:
        maximum = abs(float(result.get("groundwater_balance_residual_mm", 0.0)))
        nonnegative = float(result.get("groundwater_storage_mm", 0.0)) >= -tolerance
    return {"status": "passed" if maximum <= tolerance and nonnegative else "failed", "max_abs_residual_mm": maximum, "nonnegative": nonnegative}


def write_groundwater_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = output / "groundwater_report.md"
    report.write_text(
        "# Groundwater and baseflow\n\n"
        f"- model: `{result.get('model', 'linear_reservoir')}`\n"
        f"- validation: `{result.get('groundwater_validation', 'unavailable')}`\n\n"
        "Modeled groundwater storage is a conceptual reservoir state and must not be described as an observed groundwater level.\n",
        encoding="utf-8",
    )
    (output / "groundwater_report.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return report
