from __future__ import annotations

import math

import numpy as np
import pandas as pd


def scs_cn_runoff_depth_mm(rain_mm: float, curve_number: float) -> float:
    """Return direct runoff depth in mm for one rainfall increment."""
    if rain_mm <= 0:
        return 0.0
    if not 0 < curve_number <= 100:
        raise ValueError("curve_number must be in (0, 100].")

    storage_mm = 25400.0 / curve_number - 254.0
    initial_abstraction_mm = 0.2 * storage_mm
    if rain_mm <= initial_abstraction_mm:
        return 0.0
    return ((rain_mm - initial_abstraction_mm) ** 2) / (
        rain_mm - initial_abstraction_mm + storage_mm
    )


def triangular_unit_hydrograph(lag_hours: float, dt_hours: float) -> np.ndarray:
    """Create a compact triangular unit hydrograph with unit area."""
    if lag_hours <= 0 or dt_hours <= 0:
        raise ValueError("lag_hours and dt_hours must be positive.")

    peak_hours = max(dt_hours, lag_hours)
    base_hours = max(2 * dt_hours, 3 * lag_hours)
    steps = max(2, int(math.ceil(base_hours / dt_hours)) + 1)
    times = np.arange(steps) * dt_hours

    weights = np.where(
        times <= peak_hours,
        times / peak_hours,
        np.maximum(0.0, (base_hours - times) / (base_hours - peak_hours)),
    )
    if weights.sum() <= 0:
        weights[0] = 1.0
    return weights / weights.sum()


def runoff_to_flow_cms(
    rainfall: pd.DataFrame,
    subcatchments: pd.DataFrame,
    dt_hours: float,
) -> pd.DataFrame:
    """Compute routed subcatchment runoff hydrographs and total inflow."""
    if dt_hours <= 0:
        raise ValueError("dt_hours must be positive.")
    if rainfall.empty:
        raise ValueError("Rainfall data must contain at least one row.")
    if subcatchments.empty:
        raise ValueError("Subcatchments data must contain at least one row.")

    unit_hydrographs = {
        row.id: triangular_unit_hydrograph(float(row.lag_hours), dt_hours)
        for row in subcatchments.itertuples(index=False)
    }
    extra_steps = max(len(uh) for uh in unit_hydrographs.values()) - 1
    times = pd.date_range(
        start=rainfall["time"].iloc[0],
        periods=len(rainfall) + extra_steps,
        freq=pd.to_timedelta(dt_hours, unit="h"),
    )
    result = pd.DataFrame({"time": times})
    total = np.zeros(len(result), dtype=float)

    for row in subcatchments.itertuples(index=False):
        runoff_mm = np.array(
            [scs_cn_runoff_depth_mm(v, float(row.curve_number)) for v in rainfall["rain_mm"]]
        )
        volume_m3 = runoff_mm / 1000.0 * float(row.area_km2) * 1_000_000.0
        direct_flow_cms = volume_m3 / (dt_hours * 3600.0)
        routed_full = np.convolve(direct_flow_cms, unit_hydrographs[row.id], mode="full")
        routed = np.zeros(len(result), dtype=float)
        routed[: len(routed_full)] = routed_full
        column = f"subcatchment_{row.id}_flow_cms"
        result[column] = routed
        total += routed

    result["inflow_cms"] = total
    return result
