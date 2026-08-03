from __future__ import annotations

from pathlib import Path
from typing import Any
import pandas as pd


def collect_all_continuous_fluxes(output_dir: str | Path) -> pd.DataFrame:
    return pd.read_csv(Path(output_dir) / "daily_fluxes.csv", parse_dates=["date"])


def calculate_daily_component_balance(data: pd.DataFrame) -> pd.DataFrame:
    columns = [name for name in data.columns if name.endswith("_mm") or name.endswith("_m3")]
    return data[[name for name in ("date", "subbasin_id", *columns) if name in data]].copy()


def _aggregate(data: pd.DataFrame, frequency: str) -> pd.DataFrame:
    frame = data.copy(); frame["period"] = pd.to_datetime(frame.date).dt.to_period(frequency).astype(str)
    values = [name for name in frame if name.endswith("_mm") or name.endswith("_m3")]
    return frame.groupby(["period", "subbasin_id"], as_index=False)[values].sum(numeric_only=True)


def calculate_monthly_component_balance(data: pd.DataFrame) -> pd.DataFrame: return _aggregate(data, "M")
def calculate_annual_component_balance(data: pd.DataFrame) -> pd.DataFrame: return _aggregate(data, "Y")
def calculate_period_component_balance(data: pd.DataFrame) -> pd.DataFrame: return data.groupby("subbasin_id", as_index=False).sum(numeric_only=True)


def identify_unreported_fluxes(result: dict[str, Any] | pd.DataFrame) -> list[str]:
    data = result["fluxes"] if isinstance(result, dict) else result
    expected = {"interception_evaporation_mm", "actual_et_mm", "surface_runoff_mm", "interflow_mm", "baseflow_mm", "deep_loss_mm", "storage_change_mm"}
    return sorted(expected - set(data.columns))


def detect_double_counted_fluxes(result: dict[str, Any] | pd.DataFrame) -> list[str]:
    data = result["fluxes"] if isinstance(result, dict) else result
    return ["runoff_to_channel_mm is a reporting aggregate, not an additional water-balance outflow"] if "runoff_to_channel_mm" in data else []


def detect_omitted_fluxes(result: dict[str, Any] | pd.DataFrame) -> list[str]: return identify_unreported_fluxes(result)


def reconcile_reported_and_internal_fluxes(result: dict[str, Any] | pd.DataFrame) -> dict[str, Any]:
    data = result["fluxes"] if isinstance(result, dict) else result
    return {"status": "passed" if not identify_unreported_fluxes(data) and float(data.water_balance_residual_mm.abs().max()) <= 1e-6 else "failed", "unreported_fluxes": identify_unreported_fluxes(data), "maximum_daily_residual_mm": float(data.water_balance_residual_mm.abs().max()), "cumulative_residual_mm": float(data.water_balance_residual_mm.sum())}


def write_continuous_balance_audit(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True); data = result["daily"]
    data.to_csv(output / "daily_complete_ledger.csv", index=False)
    with pd.ExcelWriter(output / "monthly_complete_ledger.xlsx") as writer: result["monthly"].to_excel(writer, index=False)
    with pd.ExcelWriter(output / "annual_complete_ledger.xlsx") as writer: result["annual"].to_excel(writer, index=False)
    pd.DataFrame({"unreported_flux": result["reconciliation"]["unreported_fluxes"]}).to_excel(output / "unreported_fluxes.xlsx", index=False)
    (output / "balance_audit_report.md").write_text("# Complete flux ledger\n\n" + str(result["reconciliation"]) + "\n", encoding="utf-8")
    return {"daily": output / "daily_complete_ledger.csv", "report": output / "balance_audit_report.md"}
