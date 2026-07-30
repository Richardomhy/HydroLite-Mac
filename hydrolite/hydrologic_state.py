from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def _values(data: Any, names: tuple[str, ...]) -> pd.Series:
    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data or [])
    column = next((name for name in names if name in frame), None)
    return pd.to_numeric(frame[column], errors="coerce") if column else pd.Series(dtype=float)


def estimate_antecedent_precipitation_index(data: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    values = _values(data, ("rainfall_mm", "rain_mm", "precipitation_mm")).fillna(0)
    decay = float((config or {}).get("api_decay", 0.85))
    api = 0.0
    for value in values:
        api = decay * api + float(value)
    return {"value": api, "unit": "mm", "method": "exponential_api", "source": "observed_rainfall" if len(values) else "missing"}


def estimate_initial_soil_moisture(data: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    api = estimate_antecedent_precipitation_index(data, config)["value"]
    scale = float((config or {}).get("soil_moisture_api_scale_mm", 100.0))
    return {"value": min(1.0, max(0.0, api / max(scale, 1e-6))), "unit": "fraction", "method": "api_proxy", "source": "estimated"}


def estimate_initial_abstraction_state(data: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    soil = estimate_initial_soil_moisture(data, config)["value"]
    return {"value": max(0.0, 1.0 - soil), "unit": "fraction_remaining", "method": "soil_moisture_proxy", "source": "estimated"}


def estimate_initial_baseflow(data: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    values = _values(data, ("flow_cms", "observed_streamflow_m3s", "outflow_cms")).dropna().head(3)
    return {"value": float(values.median()) if len(values) else None, "unit": "m3/s", "method": "observed_window" if len(values) else "missing", "source": "observed" if len(values) else "unavailable"}


def estimate_initial_reach_storage(data: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    flow = estimate_initial_baseflow(data, config)["value"]
    k_hours = float((config or {}).get("reach_k_hours", 1.0))
    return {"value": None if flow is None else max(0.0, flow * k_hours * 3600), "unit": "m3", "method": "muskingum_storage_proxy", "source": "estimated"}


def estimate_initial_reservoir_storage(data: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    values = _values(data, ("reservoir_storage_m3", "storage_m3")).dropna().head(3)
    return {"value": float(values.median()) if len(values) else None, "unit": "m3", "method": "observed_window" if len(values) else "missing", "source": "observed" if len(values) else "unavailable"}


def build_initial_state(event: dict[str, Any], data: dict[str, Any], project: Any = None) -> dict[str, Any]:
    rainfall = data.get("rainfall", pd.DataFrame())
    flow = data.get("flow", pd.DataFrame())
    reservoir = data.get("reservoir", pd.DataFrame())
    stage_values = _values(data.get("stage", pd.DataFrame()), ("stage_m", "water_level_m")).dropna().head(3)
    api = estimate_antecedent_precipitation_index(rainfall)
    soil = estimate_initial_soil_moisture(rainfall)
    baseflow = estimate_initial_baseflow(flow)
    reach_storage = estimate_initial_reach_storage(flow)
    reservoir_storage = estimate_initial_reservoir_storage(reservoir)
    source = "observed" if baseflow["value"] is not None else "parameterized_estimate"
    state = {
        "event_id": event["event_id"],
        "antecedent_precipitation_index": api["value"],
        "soil_moisture_proxy": soil["value"],
        "initial_abstraction_state": estimate_initial_abstraction_state(rainfall)["value"],
        "initial_baseflow_cms": baseflow["value"],
        "initial_reach_flow_cms": baseflow["value"],
        "initial_reach_storage_m3": reach_storage["value"],
        "reservoir_stage_m": float(stage_values.median()) if len(stage_values) else None,
        "reservoir_storage_m3": reservoir_storage["value"],
        "snow_state": None,
        "uncertainty": "exploratory",
        "method": "observed_then_parameterized",
        "source": source,
        "demo_default_used": source != "observed",
    }
    state["validation"] = validate_initial_state(state)
    return state


def validate_initial_state(state: dict[str, Any]) -> dict[str, Any]:
    errors = []
    for name in ("initial_baseflow_cms", "initial_reach_storage_m3", "reservoir_storage_m3"):
        value = state.get(name)
        if value is not None and float(value) < 0:
            errors.append(f"{name} must be non-negative")
    moisture = state.get("soil_moisture_proxy")
    if moisture is not None and not 0 <= float(moisture) <= 1:
        errors.append("soil_moisture_proxy must be in [0, 1]")
    warnings = ["Demo/parameterized initial state cannot support real validation."] if state.get("demo_default_used") else []
    return {"status": "passed" if not errors else "failed", "errors": errors, "warnings": warnings}


def write_initial_state_report(output_dir: str | Path, result: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = result if isinstance(result, list) else [result]
    xlsx = output / "event_initial_states.xlsx"
    pd.DataFrame(rows).drop(columns=["validation"], errors="ignore").to_excel(xlsx, index=False)
    yaml_path = output / "initial_states.yaml"
    yaml_path.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    report = output / "initial_state_report.md"
    report.write_text(
        "# Hydrologic Initial State Report\n\n"
        f"- Events: `{len(rows)}`\n"
        "- Source priority: observed, continuous-model result, antecedent meteorology, parameterized estimate, demo default.\n"
        "- Demo defaults are explicitly flagged and cannot establish real-data validation.\n",
        encoding="utf-8",
    )
    return {"xlsx": xlsx, "yaml": yaml_path, "report": report}
