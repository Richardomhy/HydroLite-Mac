from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FLOW_FACTORS = {"m3/s": 86400.0, "m3/d": 1.0, "l/s": 86.4, "mm/d": None}


def infer_flow_units(data: pd.DataFrame) -> str:
    for name in ("streamflow_cms", "flow_cms", "discharge_cms"):
        if name in data: return "m3/s"
    return "unknown"


def convert_observed_flow_to_volume(data: pd.DataFrame, basin_area_km2: float, unit: str | None = None) -> pd.DataFrame:
    unit = unit or infer_flow_units(data)
    value_column = next((name for name in ("streamflow_cms", "flow_cms", "discharge_cms", "flow") if name in data), None)
    if value_column is None or unit not in FLOW_FACTORS: raise ValueError("Observed flow requires a recognised discharge column and declared units.")
    values = pd.to_numeric(data[value_column], errors="coerce")
    if values.isna().any() or (values < 0).any(): raise ValueError("Observed flow must be finite and non-negative; missing values are not filled with zero.")
    volume = values * FLOW_FACTORS[unit] if unit != "mm/d" else values * float(basin_area_km2) * 1000.0
    result = data.copy(); result["observed_volume_m3_d"] = volume; result["observed_runoff_depth_mm_d"] = volume / (float(basin_area_km2) * 1000.0); result["flow_unit"] = unit
    return result


def audit_observed_streamflow(data: pd.DataFrame, basin_area_km2: float) -> dict[str, Any]:
    converted = convert_observed_flow_to_volume(data, basin_area_km2)
    dates = pd.to_datetime(converted["date"], errors="coerce")
    return {"status": "passed" if dates.notna().all() and not dates.duplicated().any() else "failed", "unit": infer_flow_units(data), "records": len(converted), "start": str(dates.min().date()), "end": str(dates.max().date()), "total_volume_m3": float(converted.observed_volume_m3_d.sum()), "equivalent_runoff_depth_mm": float(converted.observed_runoff_depth_mm_d.sum()), "runoff_coefficient": None, "converted": converted}


def write_flow_observation_audit(output_dir: str | Path, result: dict[str, Any], simulated: pd.DataFrame | None = None) -> Path:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    summary = {key: value for key, value in result.items() if key != "converted"}
    with pd.ExcelWriter(output / "flow_observation_audit.xlsx") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="summary", index=False); result["converted"].to_excel(writer, sheet_name="converted", index=False)
    if simulated is not None and not simulated.empty:
        fig, ax = plt.subplots(figsize=(8, 3)); ax.bar(["observed", "simulated"], [result["total_volume_m3"], float(simulated["outflow_m3"].sum())]); ax.set_ylabel("volume (m3)"); fig.tight_layout(); fig.savefig(output / "observed_simulated_volume.png", dpi=120); plt.close(fig)
    return output / "flow_observation_audit.xlsx"
