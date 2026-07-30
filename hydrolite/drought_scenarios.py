from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hydrolite.drought_forecast_contracts import validate_drought_forecast_forcing


def create_climatology_scenario(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    value_columns = [column for column in ("precipitation_mm", "temperature_mean_c", "potential_et_mm") if column in frame]
    climatology = frame.groupby([frame["date"].dt.month, "subbasin_id"])[value_columns].mean().rename_axis(["month", "subbasin_id"]).reset_index()
    result = frame[["date", "subbasin_id"]].copy()
    result["month"] = result["date"].dt.month
    result = result.merge(climatology, on=["month", "subbasin_id"]).drop(columns="month")
    result["scenario_type"] = "climatology"
    result["member_id"] = "climatology"
    return result


def create_precipitation_scale_scenarios(data: pd.DataFrame, factors: list[float]) -> pd.DataFrame:
    rows = []
    for factor in factors:
        if factor < 0:
            raise ValueError("precipitation scale factor must be non-negative")
        frame = data.copy()
        frame["precipitation_mm"] = pd.to_numeric(frame["precipitation_mm"]) * factor
        frame["scenario_type"] = "user_scenario"
        frame["member_id"] = f"precip_{factor:.2f}"
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def create_temperature_scenarios(data: pd.DataFrame, offsets: list[float]) -> pd.DataFrame:
    rows = []
    for offset in offsets:
        frame = data.copy()
        for column in ("temperature_min_c", "temperature_max_c", "temperature_mean_c"):
            if column in frame:
                frame[column] = pd.to_numeric(frame[column]) + offset
        frame["scenario_type"] = "user_scenario"; frame["member_id"] = f"temperature_{offset:+.1f}C"; rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def create_pet_scenarios(data: pd.DataFrame, factors: list[float]) -> pd.DataFrame:
    if "potential_et_mm" not in data:
        raise ValueError("potential_et_mm is required for PET scale scenarios")
    rows = []
    for factor in factors:
        if factor < 0: raise ValueError("PET scale factor must be non-negative")
        frame = data.copy(); frame["potential_et_mm"] = pd.to_numeric(frame["potential_et_mm"]) * factor
        frame["scenario_type"] = "user_scenario"; frame["member_id"] = f"pet_{factor:.2f}"; rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def create_season_shift_scenarios(data: pd.DataFrame, shifts: list[int]) -> pd.DataFrame:
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    rows = []
    for shift in shifts:
        part = frame.copy()
        part["date"] = part["date"] + pd.to_timedelta(int(shift), unit="D")
        part["scenario_type"] = "user_scenario"; part["member_id"] = f"season_shift_{shift:+d}d"; rows.append(part)
    return pd.concat(rows, ignore_index=True)


def load_external_drought_forecast(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    validation = validate_drought_forecast_forcing(frame)
    if validation["status"] != "passed":
        raise ValueError(f"Invalid external drought forecast: {validation['missing'] + validation['errors']}")
    return frame


def generate_drought_scenario_ensemble(config: dict[str, Any]) -> pd.DataFrame:
    source = pd.read_csv(config["source_csv"])
    frames = [source.assign(scenario_type="synthetic_demo", member_id="baseline")]
    frames.append(create_precipitation_scale_scenarios(source, config.get("precipitation_factors", [0.8, 0.6])))
    frames.append(create_temperature_scenarios(source, config.get("temperature_offsets_c", [1.0, 2.0])))
    if "potential_et_mm" in source:
        frames.append(create_pet_scenarios(source, config.get("pet_factors", [1.15])))
    frames.append(create_season_shift_scenarios(source, config.get("season_shifts_days", [30])))
    dry = source.copy()
    dry["precipitation_mm"] = pd.to_numeric(dry["precipitation_mm"]) * float(config.get("dry_analogue_factor", 0.5))
    dry["scenario_type"] = "synthetic_demo"; dry["member_id"] = "dry_historical_analogue"
    frames.append(dry)
    return pd.concat(frames, ignore_index=True)


def validate_drought_scenarios(result: pd.DataFrame) -> dict[str, Any]:
    required = {"date", "subbasin_id", "precipitation_mm", "member_id", "scenario_type"}
    missing = sorted(required - set(result))
    errors = []
    if not missing and (pd.to_numeric(result["precipitation_mm"], errors="coerce") < 0).any():
        errors.append("negative precipitation")
    return {"status": "passed" if not missing and not errors else "failed", "missing": missing, "errors": errors, "members": int(result["member_id"].nunique()) if "member_id" in result else 0}


def write_drought_scenario_report(output_dir: str | Path, result: pd.DataFrame) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    path = output / "forcing_members.csv"; result.to_csv(path, index=False)
    report = output / "drought_scenario_report.md"
    report.write_text(
        "# Drought scenario ensemble\n\n"
        f"- members: `{result['member_id'].nunique()}`\n- scenario types: `{sorted(result['scenario_type'].unique())}`\n\n"
        "User scenarios and synthetic demos are scenario simulations, not meteorological forecasts.\n",
        encoding="utf-8",
    )
    return {"forcing": path, "report": report}
