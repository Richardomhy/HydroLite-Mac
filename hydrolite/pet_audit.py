from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def audit_temperature_units(data: pd.DataFrame) -> dict[str, Any]:
    cols = [name for name in ("temperature_min_c", "temperature_max_c", "temperature_mean_c") if name in data]
    values = pd.to_numeric(data[cols].stack(), errors="coerce") if cols else pd.Series(dtype=float)
    return {"status": "passed" if not values.empty and values.between(-90, 70).all() else "failed", "columns": cols, "min_c": float(values.min()) if len(values) else None, "max_c": float(values.max()) if len(values) else None}


def audit_latitude_value(latitude: float) -> dict[str, Any]:
    value = float(latitude)
    return {"status": "passed" if -90 <= value <= 90 else "failed", "latitude_degrees": value, "latitude_radians": float(np.radians(value))}


def audit_day_of_year(data: pd.DataFrame) -> dict[str, Any]:
    dates = pd.to_datetime(data["date"], errors="coerce")
    days = dates.dt.dayofyear
    return {"status": "passed" if dates.notna().all() and days.between(1, 366).all() else "failed", "min_day": int(days.min()), "max_day": int(days.max()), "leap_days": int(((dates.dt.month == 2) & (dates.dt.day == 29)).sum())}


def audit_extraterrestrial_radiation(data: pd.DataFrame, latitude: float) -> pd.Series:
    dates = pd.to_datetime(data["date"])
    j = dates.dt.dayofyear.to_numpy(dtype=float)
    phi = np.radians(float(latitude))
    dr = 1 + 0.033 * np.cos(2 * np.pi * j / 365.0)
    delta = 0.409 * np.sin(2 * np.pi * j / 365.0 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws))
    return pd.Series(ra, index=data.index, name="ra_mj_m2_d")


def calculate_reference_hargreaves_independent(data: pd.DataFrame, latitude: float) -> pd.Series:
    ra = audit_extraterrestrial_radiation(data, latitude)
    tmin = pd.to_numeric(data["temperature_min_c"], errors="raise")
    tmax = pd.to_numeric(data["temperature_max_c"], errors="raise")
    tmean = pd.to_numeric(data["temperature_mean_c"], errors="raise")
    if (tmax < tmin).any():
        raise ValueError("Hargreaves audit failed: Tmax must be greater than or equal to Tmin.")
    return pd.Series(0.0023 * ra * (tmean + 17.8) * np.sqrt(tmax - tmin), index=data.index, name="independent_pet_mm")


def audit_hargreaves_equation(data: pd.DataFrame, result: pd.Series, latitude: float) -> dict[str, Any]:
    expected = calculate_reference_hargreaves_independent(data, latitude)
    actual = pd.Series(result, index=data.index, dtype=float)
    difference = (actual - expected).abs()
    return {"status": "passed" if float(difference.max()) <= 1e-9 else "implementation_error", "maximum_absolute_difference_mm": float(difference.max()), "mean_absolute_difference_mm": float(difference.mean()), "ra_units": "MJ/(m2*d)", "pet_units": "mm/d"}


def calculate_pet_climatology(pet: pd.Series) -> pd.DataFrame:
    frame = pd.DataFrame({"date": pd.to_datetime(pet.index) if isinstance(pet.index, pd.DatetimeIndex) else pd.NaT, "potential_et_mm": pet.to_numpy()})
    if frame["date"].isna().all():
        return frame.describe().T.reset_index(names="metric")
    return frame.assign(month=frame.date.dt.month).groupby("month", as_index=False).potential_et_mm.agg(["mean", "sum", "min", "max"]).reset_index()


def detect_implausible_pet(pet: pd.Series, climate_context: dict[str, Any] | None = None) -> dict[str, Any]:
    values = pd.Series(pet, dtype=float)
    mean = float(values.mean())
    maximum = float(values.max())
    status = "plausible_demo" if mean <= 10 and maximum <= 20 else "high_but_explainable" if mean <= 15 and maximum <= 25 else "implausible"
    return {"status": status, "daily_mean_pet_mm": mean, "maximum_daily_pet_mm": maximum, "negative_pet_count": int((values < 0).sum()), "days_above_10_mm": int((values > 10).sum()), "days_above_15_mm": int((values > 15).sum()), "days_above_20_mm": int((values > 20).sum()), "p01_mm": float(values.quantile(.01)), "p50_mm": float(values.quantile(.5)), "p99_mm": float(values.quantile(.99))}


def compare_pet_methods(data: pd.DataFrame, metadata: dict[str, Any]) -> dict[str, Any]:
    reference = calculate_reference_hargreaves_independent(data, float(metadata["latitude"]))
    return {"hargreaves_independent": reference, "status": detect_implausible_pet(reference)}


def write_pet_audit_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    comparison = result["comparison"].copy(); comparison.to_csv(output / "daily_pet_comparison.csv", index=False)
    monthly = comparison.assign(date=pd.to_datetime(comparison["date"]), month=lambda x: x.date.dt.month).groupby("month", as_index=False)[["model_pet_mm", "independent_pet_mm"]].agg(["mean", "sum"])
    monthly.to_excel(output / "monthly_pet_comparison.xlsx")
    pd.DataFrame([result["statistics"]]).to_excel(output / "pet_climatology.xlsx", index=False)
    comparison[["date", "model_pet_mm", "independent_pet_mm"]].to_excel(output / "previous_vs_corrected_pet.xlsx", index=False)
    fig, ax = plt.subplots(figsize=(10, 3)); ax.plot(pd.to_datetime(comparison.date), comparison.model_pet_mm, label="model"); ax.plot(pd.to_datetime(comparison.date), comparison.independent_pet_mm, alpha=.7, label="independent"); ax.legend(); ax.set_ylabel("PET (mm/d)"); fig.tight_layout(); fig.savefig(output / "pet_daily_comparison.png", dpi=120); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 3)); grouped = comparison.assign(month=pd.to_datetime(comparison.date).dt.month).groupby("month")["model_pet_mm"].mean(); ax.plot(grouped.index, grouped.values); ax.set_xlabel("month"); ax.set_ylabel("PET (mm/d)"); fig.tight_layout(); fig.savefig(output / "pet_monthly_climatology.png", dpi=120); plt.close(fig)
    text = "# PET implementation audit\n\n" + "\n".join(f"- {k}: `{v}`" for k, v in result["statistics"].items()) + "\n\nRa is daily MJ/(m2*d); Hargreaves output is mm/d. No 0.408 multiplier is used.\n"
    paths = {}
    for language, name in (("zh", "pet_audit_report_zh.md"), ("en", "pet_audit_report_en.md")):
        path = output / name; path.write_text(text, encoding="utf-8"); paths[language] = path
    return {"daily": output / "daily_pet_comparison.csv", "monthly": output / "monthly_pet_comparison.xlsx", "climatology": output / "pet_climatology.xlsx", **paths}
