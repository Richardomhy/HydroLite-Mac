from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from hydrolite.evapotranspiration import (
    calculate_fao56_reference_et,
    calculate_hargreaves_et,
    calculate_temperature_climatology_demo,
    select_pet_method,
    write_pet_report,
)
from hydrolite.routing import route_continuous_daily
from hydrolite.vegetation_state import calculate_seasonal_vegetation_factor


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "drought_model" / "continuous"
DEFAULT_PARAMETERS: dict[str, Any] = {
    "interception_capacity_mm": 2.0,
    "surface_storage_capacity_mm": 8.0,
    "upper_soil_capacity_mm": 120.0,
    "lower_soil_capacity_mm": 260.0,
    "infiltration_capacity_mm_day": 45.0,
    "infiltration_coefficient": 1.0,
    "upper_field_capacity_fraction": 0.65,
    "lower_field_capacity_fraction": 0.70,
    "percolation_coefficient": 0.04,
    "groundwater_recharge_coefficient": 0.025,
    "interflow_coefficient": 0.025,
    "baseflow_coefficient": 0.012,
    "deep_loss_coefficient": 0.001,
    "et_coefficient": 1.0,
    "initial_upper_soil_fraction": 0.60,
    "initial_lower_soil_fraction": 0.70,
    "initial_groundwater_storage_mm": 80.0,
    "initial_channel_storage_m3": 0.0,
}
STATE_FIELDS = (
    "canopy_storage_mm",
    "surface_storage_mm",
    "upper_soil_storage_mm",
    "lower_soil_storage_mm",
    "groundwater_storage_mm",
    "channel_storage_m3",
    "reservoir_storage_m3",
    "snow_storage_mm",
    "cumulative_water_balance_residual",
)


def _safe_path(path: str | Path, base: Path | None = None) -> Path:
    value = Path(path).expanduser()
    return (base / value).resolve() if base and not value.is_absolute() else value.resolve()


def create_continuous_model_config(project_dir: str | Path) -> Path:
    project = _safe_path(project_dir)
    project.mkdir(parents=True, exist_ok=True)
    path = project / "continuous_model_config.yaml"
    if path.exists():
        return path
    forcing = "daily_meteorology.csv" if (project / "daily_meteorology.csv").exists() else "data/daily_meteorology.csv"
    config = {
        "model": {"name": "HydroLite continuous conceptual model", "time_step": "daily", "synthetic_demo": False},
        "input": {"daily_meteorology_csv": forcing},
        "output": {"folder": str(DEFAULT_OUTPUT.relative_to(ROOT))},
        "pet": {"method": "auto", "latitude": 22.6, "elevation_m": 50.0},
        "warmup": {"days": 365, "method": "observed_preceding_period"},
        "routing": {"method": "linear_reservoir", "k_days": 2.0, "x": 0.2},
        "water_balance": {"daily_tolerance_mm": 1e-6, "period_tolerance_mm": 1e-4},
        "parameters": DEFAULT_PARAMETERS,
        "subbasins": [{"subbasin_id": "SB1", "area_km2": 1.0}],
        "reservoir": {"mode": "no_reservoir"},
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def load_continuous_model_config(path: str | Path) -> dict[str, Any]:
    file = _safe_path(path)
    config = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    config["_config_path"] = str(file)
    return config


def validate_continuous_model_config(config: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for key in ("input", "output", "parameters", "subbasins"):
        if key not in config:
            errors.append(f"Missing required config section: {key}")
    if config.get("model", {}).get("time_step", "daily") != "daily":
        errors.append("model.time_step must be daily for this MVP")
    parameters = {**DEFAULT_PARAMETERS, **config.get("parameters", {})}
    for key in (
        "interception_capacity_mm",
        "surface_storage_capacity_mm",
        "upper_soil_capacity_mm",
        "lower_soil_capacity_mm",
        "infiltration_capacity_mm_day",
    ):
        if float(parameters[key]) < 0:
            errors.append(f"parameters.{key} must be non-negative")
    for key in (
        "infiltration_coefficient",
        "upper_field_capacity_fraction",
        "lower_field_capacity_fraction",
        "percolation_coefficient",
        "groundwater_recharge_coefficient",
        "interflow_coefficient",
        "baseflow_coefficient",
        "deep_loss_coefficient",
        "initial_upper_soil_fraction",
        "initial_lower_soil_fraction",
    ):
        if not 0 <= float(parameters[key]) <= 1:
            errors.append(f"parameters.{key} must be between 0 and 1")
    seen = set()
    for row in config.get("subbasins", []):
        name = str(row.get("subbasin_id", "")).strip()
        if not name or name in seen:
            errors.append("Every subbasin_id must be non-empty and unique")
        seen.add(name)
        if float(row.get("area_km2", 0.0)) <= 0:
            errors.append(f"subbasin {name or '<missing>'}: area_km2 must be > 0")
    input_path = config.get("input", {}).get("daily_meteorology_csv")
    if not input_path:
        errors.append("input.daily_meteorology_csv is required")
    elif config.get("_config_path"):
        file = _safe_path(input_path, Path(config["_config_path"]).parent)
        if not file.exists():
            errors.append(f"daily meteorology file does not exist: {file}")
    pet_method = config.get("pet", {}).get("method", "auto")
    if pet_method not in {"auto", "user_supplied_pet", "FAO56_Penman_Monteith", "Hargreaves_Samani", "temperature_climatology_demo"}:
        errors.append(f"Unsupported PET method: {pet_method}")
    if not config.get("model", {}).get("synthetic_demo", False) and any(
        row.get("parameter_source", "").startswith("synthetic") for row in config.get("subbasins", [])
    ):
        warnings.append("Real project uses synthetic/default subbasin parameters; parameter_uncertain.")
    return {"status": "passed" if not errors else "failed", "errors": errors, "warnings": warnings}


def initialize_continuous_state(config: dict[str, Any], observations: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = {**DEFAULT_PARAMETERS, **config.get("parameters", {})}
    observations = observations or {}
    states: dict[str, dict[str, float]] = {}
    for row in config.get("subbasins", [{"subbasin_id": "SB1", "area_km2": 1.0}]):
        subbasin_id = str(row["subbasin_id"])
        observed = observations.get(subbasin_id, {})
        states[subbasin_id] = {
            "canopy_storage_mm": max(float(observed.get("canopy_storage_mm", 0.0)), 0.0),
            "surface_storage_mm": max(float(observed.get("surface_storage_mm", 0.0)), 0.0),
            "upper_soil_storage_mm": max(
                float(observed.get("upper_soil_storage_mm", parameters["upper_soil_capacity_mm"] * parameters["initial_upper_soil_fraction"])), 0.0
            ),
            "lower_soil_storage_mm": max(
                float(observed.get("lower_soil_storage_mm", parameters["lower_soil_capacity_mm"] * parameters["initial_lower_soil_fraction"])), 0.0
            ),
            "groundwater_storage_mm": max(
                float(observed.get("groundwater_storage_mm", parameters["initial_groundwater_storage_mm"])), 0.0
            ),
            "channel_storage_m3": max(float(observed.get("channel_storage_m3", parameters["initial_channel_storage_m3"])), 0.0),
            "reservoir_storage_m3": max(float(observed.get("reservoir_storage_m3", config.get("reservoir", {}).get("initial_storage_m3", 0.0))), 0.0),
            "snow_storage_mm": max(float(observed.get("snow_storage_mm", 0.0)), 0.0),
            "cumulative_water_balance_residual": 0.0,
        }
    return {"subbasins": states, "routing": {"channel_storage_m3": float(parameters["initial_channel_storage_m3"])}, "analysis_time": None}


def _state_storage_mm(state: dict[str, float]) -> float:
    return sum(float(state.get(name, 0.0)) for name in (
        "canopy_storage_mm", "surface_storage_mm", "upper_soil_storage_mm",
        "lower_soil_storage_mm", "groundwater_storage_mm", "snow_storage_mm",
    ))


def run_continuous_day(
    state: dict[str, float],
    forcing: dict[str, Any] | pd.Series,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    p = {**DEFAULT_PARAMETERS, **parameters}
    current = deepcopy(state)
    initial_storage = _state_storage_mm(current)
    precipitation = float(forcing.get("precipitation_mm", np.nan))
    pet = float(forcing.get("potential_et_mm", np.nan))
    if not np.isfinite(precipitation) or precipitation < 0:
        raise ValueError("precipitation_mm must be finite and non-negative; missing precipitation is not treated as zero")
    if not np.isfinite(pet) or pet < 0:
        raise ValueError("potential_et_mm must be finite and non-negative; missing PET is not treated as zero")
    warnings: list[str] = []
    temperature = forcing.get("temperature_mean_c")
    snowfall_flag = bool(forcing.get("snowfall_flag", False))
    snow_addition = 0.0
    liquid_precipitation = precipitation
    if snowfall_flag and temperature is not None and float(temperature) <= 0:
        snow_addition = precipitation
        liquid_precipitation = 0.0
        current["snow_storage_mm"] = float(current.get("snow_storage_mm", 0.0)) + snow_addition
        warnings.append("snow_status=planned: flagged snowfall retained in snow storage and not routed as rainfall")
    elif snowfall_flag:
        warnings.append("snowfall_flag present but temperature is above freezing; snow_status=planned")

    canopy_capacity = float(p["interception_capacity_mm"])
    canopy_total = float(current["canopy_storage_mm"]) + liquid_precipitation
    throughfall = max(canopy_total - canopy_capacity, 0.0)
    current["canopy_storage_mm"] = min(canopy_total, canopy_capacity)
    interception_evaporation = min(float(current["canopy_storage_mm"]), pet * 0.15)
    current["canopy_storage_mm"] -= interception_evaporation
    remaining_pet = max(pet - interception_evaporation, 0.0)

    current["surface_storage_mm"] += throughfall
    upper_space = max(float(p["upper_soil_capacity_mm"]) - float(current["upper_soil_storage_mm"]), 0.0)
    infiltration = min(
        float(current["surface_storage_mm"]),
        float(p["infiltration_capacity_mm_day"]) * float(p["infiltration_coefficient"]),
        upper_space,
    )
    current["surface_storage_mm"] -= infiltration
    current["upper_soil_storage_mm"] += infiltration
    surface_runoff = max(float(current["surface_storage_mm"]) - float(p["surface_storage_capacity_mm"]), 0.0)
    current["surface_storage_mm"] -= surface_runoff

    vegetation_factor = float(forcing.get("vegetation_factor", 1.0))
    relative_soil = (
        0.7 * float(current["upper_soil_storage_mm"]) / max(float(p["upper_soil_capacity_mm"]), 1e-9)
        + 0.3 * float(current["lower_soil_storage_mm"]) / max(float(p["lower_soil_capacity_mm"]), 1e-9)
    )
    actual_et = min(
        remaining_pet * float(p["et_coefficient"]) * max(vegetation_factor, 0.0) * float(np.clip(relative_soil, 0.0, 1.0)),
        float(current["upper_soil_storage_mm"]) + float(current["lower_soil_storage_mm"]),
    )
    upper_et = min(actual_et * 0.7, float(current["upper_soil_storage_mm"]))
    lower_et = min(actual_et - upper_et, float(current["lower_soil_storage_mm"]))
    extra_upper_et = min(
        actual_et - upper_et - lower_et,
        float(current["upper_soil_storage_mm"]) - upper_et,
    )
    actual_et = upper_et + lower_et + extra_upper_et
    current["upper_soil_storage_mm"] -= upper_et + extra_upper_et
    current["lower_soil_storage_mm"] -= lower_et

    upper_field = float(p["upper_soil_capacity_mm"]) * float(p["upper_field_capacity_fraction"])
    lower_space = max(float(p["lower_soil_capacity_mm"]) - float(current["lower_soil_storage_mm"]), 0.0)
    percolation = min(
        max(float(current["upper_soil_storage_mm"]) - upper_field, 0.0) * float(p["percolation_coefficient"]),
        lower_space,
    )
    current["upper_soil_storage_mm"] -= percolation
    current["lower_soil_storage_mm"] += percolation
    interflow = min(
        max(float(current["upper_soil_storage_mm"]) - upper_field, 0.0) * float(p["interflow_coefficient"]),
        float(current["upper_soil_storage_mm"]),
    )
    current["upper_soil_storage_mm"] -= interflow

    lower_field = float(p["lower_soil_capacity_mm"]) * float(p["lower_field_capacity_fraction"])
    groundwater_recharge = max(0.0, min(
        max(float(current["lower_soil_storage_mm"]) - lower_field, 0.0) * float(p["groundwater_recharge_coefficient"]),
        float(current["lower_soil_storage_mm"]),
    ))
    current["lower_soil_storage_mm"] -= groundwater_recharge
    current["groundwater_storage_mm"] += groundwater_recharge
    baseflow = min(float(current["groundwater_storage_mm"]) * float(p["baseflow_coefficient"]), float(current["groundwater_storage_mm"]))
    current["groundwater_storage_mm"] -= baseflow
    deep_loss = min(float(current["groundwater_storage_mm"]) * float(p["deep_loss_coefficient"]), float(current["groundwater_storage_mm"]))
    current["groundwater_storage_mm"] -= deep_loss

    final_storage = _state_storage_mm(current)
    storage_change = final_storage - initial_storage
    residual = precipitation - interception_evaporation - actual_et - surface_runoff - interflow - baseflow - deep_loss - storage_change
    current["cumulative_water_balance_residual"] = float(state.get("cumulative_water_balance_residual", 0.0)) + residual
    current["channel_storage_m3"] = float(state.get("channel_storage_m3", 0.0))
    current["reservoir_storage_m3"] = float(state.get("reservoir_storage_m3", 0.0))
    fluxes = {
        "precipitation_mm": precipitation,
        "liquid_precipitation_mm": liquid_precipitation,
        "snow_addition_mm": snow_addition,
        "potential_et_mm": pet,
        "interception_evaporation_mm": interception_evaporation,
        "actual_et_mm": actual_et,
        "infiltration_mm": infiltration,
        "percolation_mm": percolation,
        "groundwater_recharge_mm": groundwater_recharge,
        "surface_runoff_mm": surface_runoff,
        "interflow_mm": interflow,
        "baseflow_mm": baseflow,
        "deep_loss_mm": deep_loss,
        "runoff_to_channel_mm": surface_runoff + interflow + baseflow,
        "storage_change_mm": storage_change,
        "water_balance_residual_mm": residual,
    }
    return {"state": current, "fluxes": fluxes, "warnings": warnings}


def _prepare_forcing(forcing: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    data = forcing.copy()
    required = {"date", "precipitation_mm", "subbasin_id"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"Continuous forcing missing required columns: {', '.join(missing)}")
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    if data["date"].isna().any():
        raise ValueError("Continuous forcing contains unparseable dates")
    if data.duplicated(["date", "subbasin_id"]).any():
        raise ValueError("Continuous forcing must have one row per date and subbasin_id")
    data["precipitation_mm"] = pd.to_numeric(data["precipitation_mm"], errors="coerce")
    if data["precipitation_mm"].isna().any() or (data["precipitation_mm"] < 0).any():
        raise ValueError("precipitation_mm contains missing, non-numeric, or negative values")
    method = config.get("pet", {}).get("method", "auto")
    if method == "auto":
        method = select_pet_method(data)
    if method == "user_supplied_pet":
        if "potential_et_mm" not in data:
            raise ValueError("user_supplied_pet requires potential_et_mm")
        data["potential_et_mm"] = pd.to_numeric(data["potential_et_mm"], errors="coerce")
    elif method == "FAO56_Penman_Monteith":
        data["potential_et_mm"] = calculate_fao56_reference_et(data, config.get("pet", {}))
    elif method == "Hargreaves_Samani":
        data["potential_et_mm"] = calculate_hargreaves_et(data, float(config.get("pet", {}).get("latitude", 0.0)))
    elif method == "temperature_climatology_demo":
        if not config.get("model", {}).get("synthetic_demo", False):
            raise ValueError("temperature_climatology_demo is allowed only when model.synthetic_demo=true")
        data["potential_et_mm"] = calculate_temperature_climatology_demo(data)
    else:
        raise ValueError(f"Unsupported PET method: {method}")
    if data["potential_et_mm"].isna().any() or (data["potential_et_mm"] < 0).any():
        raise ValueError("potential_et_mm contains missing or negative values")
    data["vegetation_factor"] = [
        float(value) if pd.notna(value) else calculate_seasonal_vegetation_factor(date)
        for date, value in zip(data["date"], data.get("vegetation_factor", pd.Series(np.nan, index=data.index)))
    ]
    return data.sort_values(["date", "subbasin_id"]).reset_index(drop=True), {
        "method": method,
        "units": "mm/day",
        "required_inputs": [],
        "available_inputs": sorted(data.columns),
        "missing_inputs": [],
        "assumptions": ["daily time step"],
        "limitations": ["temperature_climatology_demo is synthetic only"] if method == "temperature_climatology_demo" else [],
    }


def run_continuous_period(
    forcing: pd.DataFrame,
    parameters: dict[str, Any],
    initial_state: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {"parameters": parameters, "subbasins": [{"subbasin_id": "SB1", "area_km2": 1.0}], "pet": {"method": "auto"}}
    data, pet_metadata = _prepare_forcing(forcing, config)
    state = deepcopy(initial_state)
    initial_state_snapshot = deepcopy(initial_state)
    if "subbasins" not in state:
        subbasin_id = str(data["subbasin_id"].iloc[0])
        state = {"subbasins": {subbasin_id: state}, "routing": {"channel_storage_m3": 0.0}, "analysis_time": None}
    area_lookup = {str(row["subbasin_id"]): float(row["area_km2"]) for row in config.get("subbasins", [])}
    state_rows: list[dict[str, Any]] = []
    flux_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    routing_rows: list[dict[str, Any]] = []
    routing_state = deepcopy(state.get("routing", {"channel_storage_m3": 0.0}))
    for date, day in data.groupby("date", sort=True):
        day_inflow_m3 = 0.0
        for row in day.itertuples(index=False):
            subbasin_id = str(row.subbasin_id)
            if subbasin_id not in state["subbasins"]:
                raise ValueError(f"forcing subbasin_id={subbasin_id} has no configured initial state")
            row_parameters = {**parameters, **next((item.get("parameters", {}) for item in config.get("subbasins", []) if str(item["subbasin_id"]) == subbasin_id), {})}
            result = run_continuous_day(state["subbasins"][subbasin_id], row._asdict(), row_parameters)
            state["subbasins"][subbasin_id] = result["state"]
            area = area_lookup.get(subbasin_id)
            if area is None:
                raise ValueError(f"subbasin_id={subbasin_id} is missing area_km2")
            runoff_volume = result["fluxes"]["runoff_to_channel_mm"] * area * 1000.0
            day_inflow_m3 += runoff_volume
            flux_rows.append({"date": date, "subbasin_id": subbasin_id, "area_km2": area, **result["fluxes"], "runoff_to_channel_m3": runoff_volume})
            state_rows.append({"date": date, "subbasin_id": subbasin_id, **result["state"]})
            warnings.extend(f"{date.date()} {subbasin_id}: {message}" for message in result["warnings"])
        routing_config = config.get("routing", {})
        routed = route_continuous_daily(
            day_inflow_m3,
            routing_state,
            routing_config.get("method", "linear_reservoir"),
            k_days=float(routing_config.get("k_days", 2.0)),
            x=float(routing_config.get("x", 0.2)),
            reach_id=str(routing_config.get("reach_id", "OUTLET")),
        )
        routing_state = {
            "channel_storage_m3": float(routed["final_storage_m3"]),
            "previous_inflow_m3": float(routed["previous_inflow_m3"]),
            "previous_outflow_m3": float(routed["previous_outflow_m3"]),
        }
        routing_rows.append({"date": date, **routed})
        state["analysis_time"] = pd.Timestamp(date).isoformat()
    state["routing"] = routing_state
    fluxes = pd.DataFrame(flux_rows)
    states = pd.DataFrame(state_rows)
    routing = pd.DataFrame(routing_rows)
    balance = calculate_period_water_balance({
        "fluxes": fluxes,
        "states": states,
        "routing": routing,
        "initial_state": initial_state_snapshot,
        "final_state": state,
    })
    return {
        "status": "completed",
        "forcing": data,
        "fluxes": fluxes,
        "states": states,
        "routing": routing,
        "initial_state": initial_state_snapshot,
        "final_state": state,
        "pet_metadata": pet_metadata,
        "warnings": sorted(set(warnings)),
        "water_balance": balance,
        "synthetic_demo": bool(config.get("model", {}).get("synthetic_demo", False)),
    }


def route_continuous_subbasins(results: pd.DataFrame | dict[str, Any], network: dict[str, Any]) -> pd.DataFrame:
    if isinstance(results, dict) and "routing" in results:
        return results["routing"].copy()
    frame = results.copy()
    inflow = frame.groupby("date")["runoff_to_channel_m3"].sum().sort_index()
    state: dict[str, float] = {"channel_storage_m3": float(network.get("initial_storage_m3", 0.0))}
    rows = []
    for date, value in inflow.items():
        row = route_continuous_daily(
            float(value), state, network.get("method", "linear_reservoir"),
            k_days=float(network.get("k_days", 2.0)), x=float(network.get("x", 0.2)),
        )
        rows.append({"date": date, **row})
        state = {"channel_storage_m3": row["final_storage_m3"], "previous_inflow_m3": row["previous_inflow_m3"], "previous_outflow_m3": row["previous_outflow_m3"]}
    return pd.DataFrame(rows)


def calculate_daily_water_balance(result: dict[str, Any] | pd.DataFrame) -> pd.DataFrame:
    fluxes = result["fluxes"] if isinstance(result, dict) else result
    columns = [
        "date", "subbasin_id", "precipitation_mm", "interception_evaporation_mm",
        "actual_et_mm", "surface_runoff_mm", "interflow_mm", "baseflow_mm",
        "deep_loss_mm", "storage_change_mm", "water_balance_residual_mm",
    ]
    return fluxes[[column for column in columns if column in fluxes]].copy()


def calculate_period_water_balance(result: dict[str, Any] | pd.DataFrame) -> dict[str, Any]:
    fluxes = result["fluxes"] if isinstance(result, dict) else result
    totals = {
        "total_precipitation_mm": float(fluxes["precipitation_mm"].sum()),
        "total_potential_et_mm": float(fluxes["potential_et_mm"].sum()),
        "total_interception_evaporation_mm": float(fluxes["interception_evaporation_mm"].sum()),
        "total_actual_et_mm": float(fluxes["actual_et_mm"].sum()),
        "total_surface_runoff_mm": float(fluxes["surface_runoff_mm"].sum()),
        "total_interflow_mm": float(fluxes["interflow_mm"].sum()),
        "total_baseflow_mm": float(fluxes["baseflow_mm"].sum()),
        "total_deep_loss_mm": float(fluxes["deep_loss_mm"].sum()),
        "total_storage_change_mm": float(fluxes["storage_change_mm"].sum()),
        "cumulative_water_balance_residual_mm": float(fluxes["water_balance_residual_mm"].sum()),
        "maximum_daily_residual_mm": float(fluxes["water_balance_residual_mm"].abs().max()),
    }
    if isinstance(result, dict) and "initial_state" in result and "final_state" in result:
        totals.update({
            "initial_total_storage_mm": float(sum(
                _state_storage_mm(state) for state in result["initial_state"]["subbasins"].values()
            )),
            "final_total_storage_mm": float(sum(
                _state_storage_mm(state) for state in result["final_state"]["subbasins"].values()
            )),
        })
    if isinstance(result, dict) and "routing" in result and not result["routing"].empty:
        routing = result["routing"]
        totals.update({
            "channel_initial_storage_m3": float(routing["initial_storage_m3"].iloc[0]),
            "channel_final_storage_m3": float(routing["final_storage_m3"].iloc[-1]),
            "channel_cumulative_residual_m3": float(routing["residual_m3"].sum()),
        })
    return totals


def validate_continuous_water_balance(
    result: dict[str, Any] | pd.DataFrame,
    daily_tolerance_mm: float = 1e-6,
    period_tolerance_mm: float = 1e-4,
) -> dict[str, Any]:
    fluxes = result["fluxes"] if isinstance(result, dict) else result
    period = calculate_period_water_balance(result)
    max_daily = float(fluxes["water_balance_residual_mm"].abs().max())
    cumulative = abs(float(period["cumulative_water_balance_residual_mm"]))
    routing_residual = abs(float(period.get("channel_cumulative_residual_m3", 0.0)))
    passed = max_daily <= daily_tolerance_mm and cumulative <= period_tolerance_mm and routing_residual <= 1e-6
    return {
        "status": "passed" if passed else "failed",
        "daily_tolerance_mm": daily_tolerance_mm,
        "period_tolerance_mm": period_tolerance_mm,
        "maximum_daily_residual_mm": max_daily,
        "cumulative_residual_mm": float(period["cumulative_water_balance_residual_mm"]),
        "channel_cumulative_residual_m3": float(period.get("channel_cumulative_residual_m3", 0.0)),
        "prediction_gate": "open" if passed else "closed_water_balance_failed",
    }


def _aggregate_balance(fluxes: pd.DataFrame, frequency: str) -> pd.DataFrame:
    data = fluxes.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["period"] = data["date"].dt.to_period(frequency).astype(str)
    columns = [column for column in data.columns if column.endswith("_mm") or column.endswith("_m3")]
    return data.groupby(["period", "subbasin_id"], as_index=False)[columns].sum(numeric_only=True)


def _write_chart(path: Path, frame: pd.DataFrame, columns: list[str], ylabel: str) -> None:
    available = [column for column in columns if column in frame and frame[column].notna().any()]
    if not available:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    for column in available:
        ax.plot(pd.to_datetime(frame["date"]), frame[column], label=column)
    ax.set_ylabel(ylabel)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def write_continuous_model_outputs(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = _safe_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    charts = output / "charts"
    charts.mkdir(exist_ok=True)
    daily_balance = calculate_daily_water_balance(result)
    daily_balance.to_csv(output / "daily_water_balance.csv", index=False)
    result["states"].to_csv(output / "daily_states.csv", index=False)
    result["fluxes"].to_csv(output / "daily_fluxes.csv", index=False)
    result["routing"].to_csv(output / "daily_routing.csv", index=False)
    with pd.ExcelWriter(output / "subbasin_daily_summary.xlsx") as writer:
        daily_balance.to_excel(writer, sheet_name="daily_balance", index=False)
        result["routing"].to_excel(writer, sheet_name="routing", index=False)
    _aggregate_balance(result["fluxes"], "M").to_excel(output / "monthly_water_balance.xlsx", index=False)
    _aggregate_balance(result["fluxes"], "Y").to_excel(output / "annual_water_balance.xlsx", index=False)
    merged = result["fluxes"].merge(
        result["states"][["date", "subbasin_id", "upper_soil_storage_mm", "lower_soil_storage_mm", "groundwater_storage_mm"]],
        on=["date", "subbasin_id"],
    )
    aggregate = merged.groupby("date", as_index=False).mean(numeric_only=True)
    _write_chart(charts / "precipitation_pet_timeseries.png", aggregate, ["precipitation_mm", "potential_et_mm"], "mm/day")
    _write_chart(charts / "soil_moisture_timeseries.png", aggregate, ["upper_soil_storage_mm", "lower_soil_storage_mm"], "mm")
    _write_chart(charts / "groundwater_storage_timeseries.png", aggregate, ["groundwater_storage_mm"], "mm")
    _write_chart(charts / "runoff_baseflow_timeseries.png", aggregate, ["surface_runoff_mm", "interflow_mm", "baseflow_mm"], "mm/day")
    annual = _aggregate_balance(result["fluxes"], "Y").groupby("period", as_index=False).sum(numeric_only=True)
    if not annual.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        annual.plot(x="period", y=["precipitation_mm", "actual_et_mm", "surface_runoff_mm", "baseflow_mm"], kind="bar", ax=ax)
        fig.tight_layout(); fig.savefig(charts / "annual_water_balance.png", dpi=130); plt.close(fig)
    if not result["routing"].empty:
        values = np.sort(result["routing"]["outflow_m3"].to_numpy())[::-1]
        fig, ax = plt.subplots(figsize=(7, 4)); ax.plot(np.linspace(0, 100, len(values)), values / 86400.0)
        ax.set_xlabel("Exceedance (%)"); ax.set_ylabel("Outlet flow (m3/s)")
        fig.tight_layout(); fig.savefig(charts / "flow_duration_curve.png", dpi=130); plt.close(fig)
    validation = validate_continuous_water_balance(result)
    summary = calculate_period_water_balance(result)
    manifest = {
        "status": "passed" if validation["status"] == "passed" else "failed",
        "model": "daily_semi_distributed_conceptual",
        "synthetic_demo": bool(result.get("synthetic_demo", False)),
        "start_date": str(pd.to_datetime(result["forcing"]["date"]).min().date()),
        "end_date": str(pd.to_datetime(result["forcing"]["date"]).max().date()),
        "record_days": int(result["forcing"]["date"].nunique()),
        "pet_method": result["pet_metadata"]["method"],
        "water_balance": validation,
        "summary": summary,
        "snow_status": "planned",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / "continuous_model_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    zh = output / "continuous_model_report_zh.md"
    en = output / "continuous_model_report_en.md"
    zh.write_text(
        "# HydroLite 连续水文模型报告\n\n"
        f"- 数据期：{manifest['start_date']} 至 {manifest['end_date']}，{manifest['record_days']} 日\n"
        f"- PET 方法：`{manifest['pet_method']}`\n"
        f"- 水量平衡门禁：`{validation['status']}`\n"
        f"- 累计残差：`{validation['cumulative_residual_mm']:.6g} mm`\n\n"
        "本模型为日尺度概念性水量循环 MVP；合成 Demo 不代表真实历史，模型地下水储量不等于实测地下水位。\n",
        encoding="utf-8",
    )
    en.write_text(
        "# HydroLite Continuous Hydrology Report\n\n"
        f"- Period: {manifest['start_date']} to {manifest['end_date']} ({manifest['record_days']} days)\n"
        f"- PET method: `{manifest['pet_method']}`\n"
        f"- Water-balance gate: `{validation['status']}`\n"
        f"- Cumulative residual: `{validation['cumulative_residual_mm']:.6g} mm`\n\n"
        "This is a daily conceptual water-cycle MVP. Synthetic demo data are not observed history, and modeled groundwater storage is not an observed water level.\n",
        encoding="utf-8",
    )
    write_pet_report(output, result["pet_metadata"])
    return {
        "daily_balance": output / "daily_water_balance.csv",
        "states": output / "daily_states.csv",
        "fluxes": output / "daily_fluxes.csv",
        "routing": output / "daily_routing.csv",
        "manifest": output / "continuous_model_manifest.json",
        "report_zh": zh,
        "report_en": en,
    }


def run_continuous_config(config_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    config = load_continuous_model_config(config_path)
    validation = validate_continuous_model_config(config)
    if validation["status"] != "passed":
        raise ValueError("Invalid continuous model config: " + "; ".join(validation["errors"]))
    base = Path(config["_config_path"]).parent
    forcing = pd.read_csv(_safe_path(config["input"]["daily_meteorology_csv"], base))
    state = initialize_continuous_state(config)
    result = run_continuous_period(forcing, {**DEFAULT_PARAMETERS, **config.get("parameters", {})}, state, config)
    target = _safe_path(output_dir or config.get("output", {}).get("folder", DEFAULT_OUTPUT), ROOT if output_dir is None else None)
    result["outputs"] = write_continuous_model_outputs(target, result)
    result["validation"] = validate_continuous_water_balance(
        result,
        float(config.get("water_balance", {}).get("daily_tolerance_mm", 1e-6)),
        float(config.get("water_balance", {}).get("period_tolerance_mm", 1e-4)),
    )
    return result
