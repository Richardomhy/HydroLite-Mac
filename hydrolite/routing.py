from __future__ import annotations

import logging
import math

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
    # Preserve the direct-runoff recession and give Muskingum storage enough
    # zero-inflow intervals to release.  Balances must use this full series.
    max_k = max(float(row.K_hours) for row in reaches.itertuples(index=False)) if not reaches.empty else 0.0
    tail_steps = max(0, int(math.ceil(20 * max_k / dt_hours)) + 2)
    if tail_steps and "time" in result:
        tail = pd.DataFrame(0.0, index=range(tail_steps), columns=[c for c in result.columns if c != "time"])
        tail["time"] = pd.date_range(result["time"].iloc[-1] + pd.to_timedelta(dt_hours, unit="h"), periods=tail_steps, freq=pd.to_timedelta(dt_hours, unit="h"))
        result = pd.concat([result, tail[result.columns]], ignore_index=True)
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


def route_continuous_daily(
    inflow_m3: float,
    state: dict[str, float] | None = None,
    method: str = "linear_reservoir",
    *,
    k_days: float = 2.0,
    x: float = 0.2,
    reach_id: str = "continuous_reach",
) -> dict[str, float | str]:
    """Advance a reach by one day without draining its end-of-day storage."""
    if inflow_m3 < 0:
        raise ValueError("continuous reach inflow_m3 must be non-negative")
    storage0 = max(float((state or {}).get("channel_storage_m3", 0.0)), 0.0)
    available = storage0 + float(inflow_m3)
    if method == "pass_through":
        outflow = float(inflow_m3)
        storage1 = storage0
        stability = "diagnostic_pass_through"
    elif method == "linear_reservoir":
        if k_days <= 0:
            raise ValueError(f"reach_id={reach_id}: k_days must be > 0")
        fraction = 1.0 - math.exp(-1.0 / float(k_days))
        outflow = available * fraction
        storage1 = available - outflow
        stability = "passed"
    elif method == "Muskingum":
        validate_muskingum_parameters(reach_id, float(k_days) * 24.0, float(x), 24.0)
        # A one-step Muskingum reach needs the preceding inflow/outflow. Storage
        # is retained explicitly so the daily ledger remains conservative.
        previous_inflow = float((state or {}).get("previous_inflow_m3", inflow_m3))
        previous_outflow = float((state or {}).get("previous_outflow_m3", min(available, inflow_m3)))
        denom = k_days * (1 - x) + 0.5
        c0 = (-k_days * x + 0.5) / denom
        c1 = (k_days * x + 0.5) / denom
        c2 = (k_days * (1 - x) - 0.5) / denom
        requested = max(c0 * inflow_m3 + c1 * previous_inflow + c2 * previous_outflow, 0.0)
        outflow = min(requested, available)
        storage1 = available - outflow
        stability = "passed"
    else:
        raise ValueError(f"Unsupported continuous routing method: {method}")
    residual = inflow_m3 - outflow - (storage1 - storage0)
    return {
        "reach_id": reach_id,
        "method": method,
        "inflow_m3": float(inflow_m3),
        "outflow_m3": float(outflow),
        "initial_storage_m3": storage0,
        "final_storage_m3": float(storage1),
        "residual_m3": float(residual),
        "stability": stability,
        "previous_inflow_m3": float(inflow_m3),
        "previous_outflow_m3": float(outflow),
    }


def route_continuous_series(
    inflow_m3: np.ndarray | pd.Series,
    method: str = "linear_reservoir",
    **parameters,
) -> pd.DataFrame:
    state: dict[str, float] = {"channel_storage_m3": float(parameters.pop("initial_storage_m3", 0.0))}
    rows = []
    for value in np.asarray(inflow_m3, dtype=float):
        row = route_continuous_daily(float(value), state, method, **parameters)
        rows.append(row)
        state = {
            "channel_storage_m3": float(row["final_storage_m3"]),
            "previous_inflow_m3": float(row["previous_inflow_m3"]),
            "previous_outflow_m3": float(row["previous_outflow_m3"]),
        }
    return pd.DataFrame(rows)
