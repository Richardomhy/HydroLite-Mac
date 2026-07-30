from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd


def calculate_required_warmup(config: dict[str, Any], data: pd.DataFrame) -> dict[str, Any]:
    requested = max(int(config.get("warmup", {}).get("days", 365)), 0)
    available = int(pd.to_datetime(data["date"]).nunique()) if "date" in data else len(data)
    return {
        "requested_days": requested,
        "available_days": available,
        "warmup_days": min(requested, available),
        "status": "ready" if available >= requested else "degraded_short_record",
    }


def create_warmup_forcing(data: pd.DataFrame, warmup_days: int) -> pd.DataFrame:
    if warmup_days < 0:
        raise ValueError("warmup_days must be non-negative")
    dates = pd.to_datetime(data["date"])
    unique = sorted(dates.unique())[:warmup_days]
    return data[dates.isin(unique)].copy()


def repeat_climatology_warmup(data: pd.DataFrame, years: int) -> pd.DataFrame:
    if years < 1:
        raise ValueError("years must be >= 1")
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    one_year = frame[frame["date"] < frame["date"].min() + pd.DateOffset(years=1)].copy()
    rows = []
    for cycle in range(years):
        part = one_year.copy()
        part["date"] = part["date"] + pd.DateOffset(years=cycle)
        rows.append(part)
    return pd.concat(rows, ignore_index=True)


def run_warmup(model: Callable[..., dict[str, Any]], forcing: pd.DataFrame, state: dict[str, Any], parameters: dict[str, Any] | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    result = model(forcing, parameters or {}, deepcopy(state), config)
    return {"status": "completed", "warmup_days": int(pd.to_datetime(forcing["date"]).nunique()), "result": result, "final_state": result["final_state"]}


def assess_state_convergence(states: list[dict[str, Any]] | pd.DataFrame, tolerance: float = 0.01) -> dict[str, Any]:
    if isinstance(states, pd.DataFrame):
        numeric = states.select_dtypes(include="number")
        if len(numeric) < 2:
            return {"status": "insufficient_cycles", "relative_change": None}
        before, after = numeric.iloc[-2].sum(), numeric.iloc[-1].sum()
    else:
        if len(states) < 2:
            return {"status": "insufficient_cycles", "relative_change": None}
        flatten = lambda value: sum(float(v) for row in value.get("subbasins", {}).values() for v in row.values() if isinstance(v, (int, float)))
        before, after = flatten(states[-2]), flatten(states[-1])
    relative = abs(after - before) / max(abs(before), 1e-9)
    return {"status": "converged" if relative <= tolerance else "not_converged", "relative_change": float(relative), "tolerance": tolerance}


def validate_warmup_result(result: dict[str, Any]) -> dict[str, Any]:
    valid = result.get("status") == "completed" and result.get("warmup_days", 0) > 0 and bool(result.get("final_state"))
    return {"status": "passed" if valid else "failed", "warmup_days": int(result.get("warmup_days", 0))}


def write_warmup_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "warmup_report.md"
    path.write_text(
        "# Continuous model warm-up\n\n"
        f"- status: `{result.get('status', 'unknown')}`\n"
        f"- warmup_days: `{result.get('warmup_days', 0)}`\n"
        f"- source: `{result.get('source', 'observed_preceding_period')}`\n\n"
        "Validation or test-period future observations are never used to initialize earlier states.\n",
        encoding="utf-8",
    )
    return path
