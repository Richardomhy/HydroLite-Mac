from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_rainfall(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Rainfall CSV not found: {path}")
    df = pd.read_csv(path)
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
    required = {"id", "area_km2", "curve_number", "lag_hours"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Subcatchments CSV missing columns: {sorted(missing)}")
    return df


def read_reaches(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Reaches CSV not found: {path}")
    df = pd.read_csv(path)
    required = {"id", "from", "to", "K_hours", "X"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Reaches CSV missing columns: {sorted(missing)}")
    return df


def write_summary(path: Path, summary: dict[str, float | int | str]) -> None:
    rows = [{"metric": key, "value": value} for key, value in summary.items()]
    pd.DataFrame(rows).to_excel(path, index=False)
