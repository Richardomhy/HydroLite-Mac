from __future__ import annotations

from pathlib import Path

import pandas as pd


def _alias_columns(df: pd.DataFrame, aliases: dict[str, list[str]]) -> pd.DataFrame:
    by_lower = {column.lower(): column for column in df.columns}
    for target, names in aliases.items():
        if target in df.columns:
            continue
        found = next((by_lower[name.lower()] for name in names if name.lower() in by_lower), None)
        if found is not None:
            df[target] = df[found]
    return df


def read_rainfall(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Rainfall CSV not found: {path}")
    df = pd.read_csv(path)
    if "time" not in df.columns and "datetime" in df.columns:
        df["time"] = df["datetime"]
    required = {"time", "rain_mm"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Rainfall CSV missing columns: {sorted(missing)}")
    df["time"] = pd.to_datetime(df["time"])
    return df.sort_values("time").reset_index(drop=True)


def read_subcatchments(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Subcatchments CSV not found: {path}")
    df = pd.read_csv(path)
    df = _alias_columns(
        df,
        {
            "id": ["subbasin_id"],
            "curve_number": ["cn"],
            "lag_hours": ["lag_time_hr"],
        },
    )
    required = {"id", "area_km2", "curve_number", "lag_hours"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Subcatchments CSV missing columns: {sorted(missing)}")
    return df


def read_reaches(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Reaches CSV not found: {path}")
    df = pd.read_csv(path)
    df = _alias_columns(
        df,
        {
            "id": ["reach_id"],
            "from": ["upstream_reach_id"],
            "to": ["downstream_reach_id"],
            "K_hours": ["muskingum_k_hr"],
            "X": ["muskingum_x"],
        },
    )
    required = {"id", "from", "to", "K_hours", "X"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Reaches CSV missing columns: {sorted(missing)}")
    return df


def write_summary(path: Path, summary: dict[str, float | int | str]) -> None:
    rows = [{"metric": key, "value": value} for key, value in summary.items()]
    pd.DataFrame(rows).to_excel(path, index=False)
