from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


DEFAULT_MONTHLY_FACTORS = [0.75, 0.75, 0.85, 0.95, 1.05, 1.10, 1.10, 1.05, 0.95, 0.85, 0.78, 0.75]


def load_vegetation_parameters(data: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {"method": "fixed_seasonal_coefficient", "monthly_factors": DEFAULT_MONTHLY_FACTORS, "source": "synthetic_demo_default"}
    if isinstance(data, dict):
        return dict(data)
    path = Path(data)
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    frame = pd.read_csv(path)
    return {"method": "user_supplied_vegetation_coefficient", "data": frame, "source": str(path)}


def calculate_seasonal_vegetation_factor(date: Any, land_use: str | dict[str, Any] = "mixed") -> float:
    month = pd.Timestamp(date).month
    if isinstance(land_use, dict):
        values = land_use.get("monthly_factors", DEFAULT_MONTHLY_FACTORS)
    else:
        values = DEFAULT_MONTHLY_FACTORS
    return float(values[month - 1])


def calculate_ndvi_vegetation_factor(ndvi: float, config: dict[str, Any]) -> float:
    slope = float(config.get("slope", 1.2))
    intercept = float(config.get("intercept", 0.2))
    minimum = float(config.get("minimum", 0.2))
    maximum = float(config.get("maximum", 1.2))
    return float(np.clip(intercept + slope * float(ndvi), minimum, maximum))


def validate_vegetation_factor(result: float | pd.Series) -> dict[str, Any]:
    values = np.asarray(result, dtype=float)
    valid = bool(np.all(np.isfinite(values)) and np.all(values >= 0) and np.all(values <= 2))
    return {"status": "passed" if valid else "failed", "minimum": float(np.nanmin(values)), "maximum": float(np.nanmax(values))}


def write_vegetation_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "vegetation_state_report.md"
    path.write_text(
        "# Vegetation state\n\n"
        f"- method: `{result.get('method', 'fixed_seasonal_coefficient')}`\n"
        f"- source: `{result.get('source', 'unknown')}`\n\n"
        "NDVI relationships are configurable empirical constraints, not universal vegetation laws.\n",
        encoding="utf-8",
    )
    return path
