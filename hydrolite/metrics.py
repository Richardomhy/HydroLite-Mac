from __future__ import annotations

from typing import Any

import pandas as pd


def _clean_pairs(observed: Any, simulated: Any) -> tuple[pd.Series, pd.Series]:
    obs = pd.to_numeric(pd.Series(observed), errors="coerce")
    sim = pd.to_numeric(pd.Series(simulated), errors="coerce")
    data = pd.DataFrame({"observed": obs, "simulated": sim}).dropna()
    return data["observed"], data["simulated"]


def _insufficient(observed: pd.Series, simulated: pd.Series, min_count: int = 2) -> bool:
    return len(observed) < min_count or len(simulated) < min_count


def nse(observed: Any, simulated: Any) -> float | pd.NA:
    obs, sim = _clean_pairs(observed, simulated)
    if _insufficient(obs, sim):
        return pd.NA
    denominator = ((obs - obs.mean()) ** 2).sum()
    if denominator == 0:
        return pd.NA
    return float(1 - ((sim - obs) ** 2).sum() / denominator)


def rmse(observed: Any, simulated: Any) -> float | pd.NA:
    obs, sim = _clean_pairs(observed, simulated)
    if _insufficient(obs, sim, min_count=1):
        return pd.NA
    return float((((sim - obs) ** 2).mean()) ** 0.5)


def mae(observed: Any, simulated: Any) -> float | pd.NA:
    obs, sim = _clean_pairs(observed, simulated)
    if _insufficient(obs, sim, min_count=1):
        return pd.NA
    return float((sim - obs).abs().mean())


def pbias(observed: Any, simulated: Any) -> float | pd.NA:
    obs, sim = _clean_pairs(observed, simulated)
    if _insufficient(obs, sim, min_count=1):
        return pd.NA
    denominator = obs.sum()
    if denominator == 0:
        return pd.NA
    return float(100.0 * (sim - obs).sum() / denominator)


def r2(observed: Any, simulated: Any) -> float | pd.NA:
    obs, sim = _clean_pairs(observed, simulated)
    if _insufficient(obs, sim):
        return pd.NA
    if obs.std(ddof=0) == 0 or sim.std(ddof=0) == 0:
        return pd.NA
    corr = obs.corr(sim)
    if pd.isna(corr):
        return pd.NA
    return float(corr**2)


def kge(observed: Any, simulated: Any) -> float | pd.NA:
    obs, sim = _clean_pairs(observed, simulated)
    if _insufficient(obs, sim):
        return pd.NA
    obs_mean = obs.mean()
    sim_mean = sim.mean()
    obs_std = obs.std(ddof=0)
    sim_std = sim.std(ddof=0)
    if obs_mean == 0 or obs_std == 0:
        return pd.NA
    corr = obs.corr(sim)
    if pd.isna(corr):
        return pd.NA
    alpha = sim_std / obs_std
    beta = sim_mean / obs_mean
    return float(1 - (((corr - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2) ** 0.5))


def metric_warnings(observed: Any, simulated: Any) -> list[str]:
    obs, sim = _clean_pairs(observed, simulated)
    warnings: list[str] = []
    if len(obs) < 2:
        warnings.append("Fewer than two valid observed/simulated pairs; correlation-based metrics may be NA.")
    if len(obs) and obs.sum() == 0:
        warnings.append("Observed flow sum is zero; PBIAS is NA.")
    if len(obs) and obs.std(ddof=0) == 0:
        warnings.append("Observed flow variance is zero; NSE/R2/KGE may be NA.")
    return warnings


def calculate_all_metrics(observed: Any, simulated: Any) -> dict[str, Any]:
    obs, sim = _clean_pairs(observed, simulated)
    return {
        "n_pairs": int(len(obs)),
        "NSE": nse(obs, sim),
        "RMSE": rmse(obs, sim),
        "MAE": mae(obs, sim),
        "PBIAS": pbias(obs, sim),
        "R2": r2(obs, sim),
        "KGE": kge(obs, sim),
        "warnings": metric_warnings(obs, sim),
    }
