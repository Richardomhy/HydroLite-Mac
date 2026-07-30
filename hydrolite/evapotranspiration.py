from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd


PET_METHODS = (
    "user_supplied_pet",
    "FAO56_Penman_Monteith",
    "Hargreaves_Samani",
    "temperature_climatology_demo",
)


def normalize_pet_units(data: pd.Series | np.ndarray | float, unit: str = "mm/day"):
    values = np.asarray(data, dtype=float)
    aliases = {"mm/day": 1.0, "mm/d": 1.0, "mm": 1.0, "m/day": 1000.0, "m/d": 1000.0}
    if unit not in aliases:
        raise ValueError(f"Unsupported PET unit {unit!r}; expected mm/day or m/day.")
    result = values * aliases[unit]
    if np.any(~np.isfinite(result)) or np.any(result < 0):
        raise ValueError("PET must contain finite, non-negative values.")
    if np.ndim(data) == 0:
        return float(result)
    return pd.Series(result, index=getattr(data, "index", None), name="potential_et_mm")


def validate_pet_inputs(data: pd.DataFrame, method: str) -> dict[str, Any]:
    required = {
        "user_supplied_pet": ["potential_et_mm"],
        "FAO56_Penman_Monteith": [
            "temperature_mean_c",
            "solar_radiation_mj_m2_d",
            "relative_humidity_percent",
            "wind_speed_m_s",
        ],
        "Hargreaves_Samani": ["temperature_min_c", "temperature_max_c", "temperature_mean_c"],
        "temperature_climatology_demo": ["temperature_mean_c"],
    }
    if method not in required:
        return {"status": "failed", "method": method, "required_inputs": [], "missing_inputs": [f"unknown method: {method}"]}
    missing = [column for column in required[method] if column not in data]
    invalid = []
    if not missing:
        values = data[required[method]].apply(pd.to_numeric, errors="coerce")
        if values.isna().any().any():
            invalid.append("required PET inputs contain missing or non-numeric values")
    return {
        "status": "passed" if not missing and not invalid else "failed",
        "method": method,
        "required_inputs": required[method],
        "available_inputs": sorted(set(required[method]) & set(data.columns)),
        "missing_inputs": missing,
        "errors": invalid,
    }


def select_pet_method(data_availability: pd.DataFrame | set[str] | list[str]) -> str:
    columns = set(data_availability.columns if isinstance(data_availability, pd.DataFrame) else data_availability)
    if "potential_et_mm" in columns:
        return "user_supplied_pet"
    pm = {"temperature_mean_c", "solar_radiation_mj_m2_d", "relative_humidity_percent", "wind_speed_m_s"}
    if pm <= columns:
        return "FAO56_Penman_Monteith"
    if {"temperature_min_c", "temperature_max_c", "temperature_mean_c"} <= columns:
        return "Hargreaves_Samani"
    return "temperature_climatology_demo"


def calculate_hargreaves_et(data: pd.DataFrame, latitude: float) -> pd.Series:
    check = validate_pet_inputs(data, "Hargreaves_Samani")
    if check["status"] != "passed":
        raise ValueError(f"Hargreaves inputs invalid: {check['missing_inputs'] + check['errors']}")
    dates = pd.to_datetime(data["date"] if "date" in data else data.index)
    day = (dates.dt.dayofyear if isinstance(dates, pd.Series) else dates.dayofyear).to_numpy()
    phi = np.radians(float(latitude))
    dr = 1 + 0.033 * np.cos(2 * np.pi * day / 365)
    delta = 0.409 * np.sin(2 * np.pi * day / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws)
    )
    tmin = pd.to_numeric(data["temperature_min_c"]).to_numpy()
    tmax = pd.to_numeric(data["temperature_max_c"]).to_numpy()
    tmean = pd.to_numeric(data["temperature_mean_c"]).to_numpy()
    pet = 0.0023 * (tmean + 17.8) * np.sqrt(np.maximum(tmax - tmin, 0)) * ra
    return pd.Series(np.maximum(pet, 0), index=data.index, name="potential_et_mm")


def calculate_fao56_reference_et(data: pd.DataFrame, metadata: dict[str, Any]) -> pd.Series:
    check = validate_pet_inputs(data, "FAO56_Penman_Monteith")
    if check["status"] != "passed":
        raise ValueError(f"FAO56 Penman-Monteith inputs invalid: {check['missing_inputs'] + check['errors']}")
    t = pd.to_numeric(data["temperature_mean_c"]).to_numpy()
    radiation = pd.to_numeric(data["solar_radiation_mj_m2_d"]).to_numpy()
    humidity = np.clip(pd.to_numeric(data["relative_humidity_percent"]).to_numpy(), 0, 100)
    wind = np.maximum(pd.to_numeric(data["wind_speed_m_s"]).to_numpy(), 0)
    elevation = float(metadata.get("elevation_m", 0.0))
    pressure = (
        pd.to_numeric(data["pressure_kpa"]).to_numpy()
        if "pressure_kpa" in data
        else np.full(len(data), 101.3 * ((293 - 0.0065 * elevation) / 293) ** 5.26)
    )
    es = 0.6108 * np.exp(17.27 * t / (t + 237.3))
    ea = es * humidity / 100
    delta = 4098 * es / (t + 237.3) ** 2
    gamma = 0.000665 * pressure
    net_radiation = 0.77 * radiation
    pet = (0.408 * delta * net_radiation + gamma * (900 / (t + 273)) * wind * (es - ea)) / (
        delta + gamma * (1 + 0.34 * wind)
    )
    return pd.Series(np.maximum(pet, 0), index=data.index, name="potential_et_mm")


def calculate_temperature_climatology_demo(data: pd.DataFrame) -> pd.Series:
    if "temperature_mean_c" not in data:
        raise ValueError("temperature_mean_c is required for the demo PET climatology.")
    temperature = pd.to_numeric(data["temperature_mean_c"], errors="coerce")
    if temperature.isna().any():
        raise ValueError("temperature_mean_c contains missing or non-numeric values.")
    return pd.Series(np.maximum(0.5, 1.5 + 0.08 * temperature), index=data.index, name="potential_et_mm")


def calculate_actual_et(
    pet: float,
    soil_state: dict[str, float],
    vegetation: float | dict[str, Any],
    config: dict[str, Any],
) -> float:
    if pet < 0:
        raise ValueError("PET must be non-negative.")
    upper = max(float(soil_state.get("upper_soil_storage_mm", 0.0)), 0.0)
    lower = max(float(soil_state.get("lower_soil_storage_mm", 0.0)), 0.0)
    upper_capacity = max(float(config.get("upper_soil_capacity_mm", 100.0)), 1e-9)
    lower_capacity = max(float(config.get("lower_soil_capacity_mm", 200.0)), 1e-9)
    factor = float(vegetation.get("factor", 1.0) if isinstance(vegetation, dict) else vegetation)
    stress = np.clip((upper / upper_capacity) * 0.7 + (lower / lower_capacity) * 0.3, 0.0, 1.0)
    return float(min(pet * max(factor, 0.0) * stress * float(config.get("et_coefficient", 1.0)), upper + lower))


def write_pet_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "pet_method_report.md"
    payload = {key: value for key, value in result.items() if key != "values"}
    path.write_text(
        "# Evapotranspiration method\n\n"
        f"- method: `{payload.get('method', 'unknown')}`\n"
        f"- units: `{payload.get('units', 'mm/day')}`\n"
        f"- missing inputs: `{payload.get('missing_inputs', [])}`\n"
        f"- assumptions: `{payload.get('assumptions', [])}`\n"
        f"- limitations: `{payload.get('limitations', [])}`\n\n"
        "Penman-Monteith is used only when its required inputs are present. Demo climatology is synthetic and is not an observed PET product.\n",
        encoding="utf-8",
    )
    (output / "pet_method.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
