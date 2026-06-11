from __future__ import annotations

import logging

import numpy as np
import pandas as pd


def _muskingum_error(reach_id: str, dt_hours: float, k_hours: float, x: float, condition: str) -> ValueError:
    return ValueError(
        "Invalid Muskingum parameters "
        f"for reach_id={reach_id}: dt={dt_hours} hours, K={k_hours} hours, X={x}. "
        f"Violated condition: {condition}. "
        "Please adjust dt, K, or X."
    )


def validate_muskingum_parameters(
    reach_id: str,
    k_hours: float,
    x: float,
    dt_hours: float,
) -> None:
    # HydroLite stores both dt and Muskingum K in hours, so the stability bounds
    # below are dimensionally consistent.
    if dt_hours <= 0:
        raise _muskingum_error(reach_id, dt_hours, k_hours, x, "dt > 0")
    if k_hours <= 0:
        raise _muskingum_error(reach_id, dt_hours, k_hours, x, "K > 0")
    if x < 0:
        raise _muskingum_error(reach_id, dt_hours, k_hours, x, "0 <= X")
    if x > 0.5:
        raise _muskingum_error(reach_id, dt_hours, k_hours, x, "X <= 0.5")

    min_dt = 2 * k_hours * x
    max_dt = 2 * k_hours * (1 - x)
    if dt_hours > max_dt:
        raise _muskingum_error(reach_id, dt_hours, k_hours, x, "dt <= 2*K*(1-X)")
    if dt_hours < min_dt:
        raise _muskingum_error(reach_id, dt_hours, k_hours, x, "dt >= 2*K*X")


def muskingum_route(
    inflow_cms: np.ndarray,
    k_hours: float,
    x: float,
    dt_hours: float,
    reach_id: str = "unknown",
) -> np.ndarray:
    validate_muskingum_parameters(reach_id, k_hours, x, dt_hours)

    denom = k_hours * (1 - x) + 0.5 * dt_hours
    c0 = (-k_hours * x + 0.5 * dt_hours) / denom
    c1 = (k_hours * x + 0.5 * dt_hours) / denom
    c2 = (k_hours * (1 - x) - 0.5 * dt_hours) / denom

    outflow = np.zeros_like(inflow_cms, dtype=float)
    outflow[0] = inflow_cms[0]
    for i in range(1, len(inflow_cms)):
        outflow[i] = c0 * inflow_cms[i] + c1 * inflow_cms[i - 1] + c2 * outflow[i - 1]
        outflow[i] = max(0.0, outflow[i])
    return outflow


def route_reaches(
    flow: pd.DataFrame,
    reaches: pd.DataFrame,
    dt_hours: float,
    logger: logging.Logger | None = None,
) -> pd.DataFrame:
    result = flow.copy()
    current = result["inflow_cms"].to_numpy(dtype=float)

    for row in reaches.itertuples(index=False):
        reach_id = str(row.id)
        k_hours = float(row.K_hours)
        x = float(row.X)
        validate_muskingum_parameters(reach_id, k_hours, x, dt_hours)
        if logger:
            logger.info(
                "Muskingum parameter check passed: reach_id=%s, dt=%s hours, K=%s hours, X=%s",
                reach_id,
                dt_hours,
                k_hours,
                x,
            )
        current = muskingum_route(current, k_hours, x, dt_hours, reach_id=reach_id)
        result[f"reach_{row.id}_outflow_cms"] = current

    result["outflow_cms"] = current
    return result
