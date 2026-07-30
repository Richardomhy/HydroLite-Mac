from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from scipy.stats import gamma as gamma_distribution
    from scipy.stats import norm
except Exception:  # pragma: no cover - exercised in dependency-light environments
    gamma_distribution = None
    norm = None


DEFAULT_SCALES = (1, 3, 6, 12, 24)


def _series(data: pd.Series | pd.DataFrame | Iterable[float], value_column: str | None = None) -> pd.Series:
    if isinstance(data, pd.Series):
        return pd.to_numeric(data, errors="coerce")
    if isinstance(data, pd.DataFrame):
        if value_column is None:
            numeric = [column for column in data.columns if column not in {"date", "subbasin_id"}]
            if len(numeric) != 1:
                raise ValueError("value_column is required when more than one value column is present")
            value_column = numeric[0]
        values = pd.to_numeric(data[value_column], errors="coerce")
        values.index = pd.to_datetime(data["date"]) if "date" in data else data.index
        return values
    return pd.Series(data, dtype=float)


def _baseline(values: pd.Series, baseline_period: tuple[Any, Any] | list[Any] | None) -> pd.Series:
    if baseline_period is None:
        return values.dropna()
    if not isinstance(values.index, pd.DatetimeIndex):
        raise ValueError("baseline_period requires a DatetimeIndex or a data frame with date")
    start, end = pd.Timestamp(baseline_period[0]), pd.Timestamp(baseline_period[1])
    return values.loc[(values.index >= start) & (values.index <= end)].dropna()


def calculate_precipitation_anomaly(data, baseline=None) -> pd.Series:
    values = _series(data)
    reference = _baseline(values, baseline)
    if reference.empty:
        raise ValueError("precipitation anomaly baseline is empty")
    result = values - reference.mean()
    result.name = "precipitation_anomaly_mm"
    return result


def _empirical_z(values: pd.Series, reference: pd.Series) -> pd.Series:
    sorted_reference = np.sort(reference.dropna().to_numpy(dtype=float))
    if len(sorted_reference) < 2:
        result = pd.Series(np.nan, index=values.index)
        result.attrs.update({"status": "limited_record", "method": "empirical_percentile"})
        return result
    percentiles = np.searchsorted(sorted_reference, values.to_numpy(dtype=float), side="right") / (len(sorted_reference) + 1)
    percentiles = np.clip(percentiles, 1 / (len(sorted_reference) + 1), len(sorted_reference) / (len(sorted_reference) + 1))
    if norm is None:
        # Rank-centered score is bounded and clearly marked as a fallback, not a fitted normal variate.
        z = (percentiles - 0.5) * 4
        method = "empirical_rank_score_no_scipy"
    else:
        z = norm.ppf(percentiles)
        method = "empirical_percentile"
    result = pd.Series(z, index=values.index)
    result[values.isna()] = np.nan
    result.attrs.update({"status": "passed", "method": method, "baseline_records": len(reference)})
    return result


def _standardized_index(
    data,
    scale: int,
    baseline_period=None,
    distribution: str = "gamma",
    *,
    allow_negative: bool = False,
    name: str,
) -> pd.Series:
    if scale < 1:
        raise ValueError("drought index scale must be >= 1 month")
    values = _series(data).rolling(scale, min_periods=scale).sum()
    reference = _baseline(values, baseline_period)
    minimum = max(20, scale * 3)
    if len(reference) < minimum:
        result = _empirical_z(values, reference)
        result.attrs.update({"status": "limited_record", "requested_distribution": distribution, "minimum_recommended_records": minimum})
        result.name = name
        return result
    if distribution == "normal":
        std = float(reference.std(ddof=0))
        result = (values - float(reference.mean())) / std if std > 0 else _empirical_z(values, reference)
        method = "normal" if std > 0 else "empirical_percentile_zero_variance"
    elif distribution == "gamma" and not allow_negative and gamma_distribution is not None:
        positive = reference[reference > 0]
        try:
            if len(positive) < minimum // 2:
                raise ValueError("too few positive values for gamma fit")
            shape, location, scale_parameter = gamma_distribution.fit(positive.to_numpy(), floc=0)
            zero_probability = float((reference <= 0).mean())
            probabilities = zero_probability + (1 - zero_probability) * gamma_distribution.cdf(np.maximum(values, 0), shape, loc=location, scale=scale_parameter)
            result = pd.Series(norm.ppf(np.clip(probabilities, 1e-6, 1 - 1e-6)), index=values.index)
            result[values.isna()] = np.nan
            method = "gamma_mixed_zero"
        except Exception as error:
            result = _empirical_z(values, reference)
            method = f"empirical_percentile_after_gamma_failure:{error}"
    elif distribution in {"empirical", "empirical_percentile"}:
        result = _empirical_z(values, reference)
        method = "empirical_percentile"
    else:
        result = _empirical_z(values, reference)
        method = f"empirical_percentile_after_unsupported_{distribution}"
    result.name = name
    result.attrs.update({"status": "passed", "method": method, "scale_months": scale, "baseline_records": len(reference)})
    return result


def calculate_spi(data, scale: int, baseline_period=None, distribution: str = "gamma") -> pd.Series:
    return _standardized_index(data, scale, baseline_period, distribution, allow_negative=False, name=f"SPI_{scale}")


def calculate_spei(precipitation, pet, scale: int, baseline_period=None, distribution: str = "normal") -> pd.Series:
    balance = _series(precipitation) - _series(pet)
    return _standardized_index(balance, scale, baseline_period, distribution, allow_negative=True, name=f"SPEI_{scale}")


def calculate_ssi(streamflow, scale: int, baseline_period=None, distribution: str = "gamma") -> pd.Series:
    return _standardized_index(streamflow, scale, baseline_period, distribution, allow_negative=False, name=f"SSI_{scale}")


def _percentile(data, baseline_period=None, name: str = "percentile") -> pd.Series:
    values = _series(data)
    reference = _baseline(values, baseline_period)
    sorted_reference = np.sort(reference.to_numpy(dtype=float))
    if not len(sorted_reference):
        raise ValueError(f"{name} baseline is empty")
    result = pd.Series(np.searchsorted(sorted_reference, values, side="right") / len(sorted_reference) * 100.0, index=values.index, name=name)
    result[values.isna()] = np.nan
    result.attrs.update({"status": "passed", "method": "empirical_percentile", "baseline_records": len(reference)})
    return result


def calculate_soil_moisture_percentile(data, baseline_period=None) -> pd.Series:
    return _percentile(data, baseline_period, "soil_moisture_percentile")


def calculate_runoff_percentile(data, baseline_period=None) -> pd.Series:
    return _percentile(data, baseline_period, "runoff_percentile")


def calculate_reservoir_storage_percentile(data, baseline_period=None) -> pd.Series:
    return _percentile(data, baseline_period, "reservoir_storage_percentile")


def calculate_groundwater_percentile(data, baseline_period=None) -> pd.Series:
    return _percentile(data, baseline_period, "groundwater_storage_percentile")


def calculate_evapotranspiration_deficit(data, actual_et=None) -> pd.Series:
    if actual_et is None and isinstance(data, pd.DataFrame):
        pet, aet = _series(data, "potential_et_mm"), _series(data, "actual_et_mm")
    else:
        pet, aet = _series(data), _series(actual_et)
    result = (pet - aet).clip(lower=0)
    result.name = "evapotranspiration_deficit_mm"
    return result


def calculate_composite_drought_index(components: pd.DataFrame | dict[str, pd.Series], weights: dict[str, float]) -> pd.Series:
    frame = pd.DataFrame(components)
    available = {name: float(weight) for name, weight in weights.items() if name in frame and frame[name].notna().any()}
    if not available:
        raise ValueError("No weighted drought components are available")
    total = sum(abs(value) for value in available.values())
    if total <= 0:
        raise ValueError("Composite drought weights must not all be zero")
    normalized = {name: value / total for name, value in available.items()}
    weighted = frame[list(normalized)].mul(pd.Series(normalized), axis=1)
    result = weighted.sum(axis=1, min_count=1)
    result.name = "composite_drought_index"
    result.attrs.update({"status": "passed", "weights": normalized, "components": list(normalized)})
    return result


def validate_drought_index(result: pd.Series | pd.DataFrame) -> dict[str, Any]:
    frame = result.to_frame() if isinstance(result, pd.Series) else result
    numeric = frame.select_dtypes(include="number")
    finite = np.isfinite(numeric.to_numpy(dtype=float)[~np.isnan(numeric.to_numpy(dtype=float))]).all() if numeric.size else False
    return {
        "status": "passed" if not frame.empty and finite else "failed",
        "records": len(frame),
        "columns": list(frame.columns),
        "missing_fraction": float(frame.isna().mean().mean()) if not frame.empty else 1.0,
    }


def write_drought_index_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    daily = result["daily"]
    monthly = result["monthly"]
    daily.to_csv(output / "drought_indices_daily.csv", index=False)
    monthly.to_csv(output / "drought_indices_monthly.csv", index=False)
    with pd.ExcelWriter(output / "drought_index_summary.xlsx") as writer:
        monthly.describe(include="all").transpose().to_excel(writer, sheet_name="summary")
        pd.DataFrame(result.get("metadata", [])).to_excel(writer, sheet_name="metadata", index=False)
    for column, filename in (
        ("SPI_12", "spi_timeseries.png"), ("SPEI_12", "spei_timeseries.png"),
        ("SSI_12", "ssi_timeseries.png"), ("soil_moisture_percentile", "soil_moisture_percentile.png"),
        ("reservoir_storage_percentile", "reservoir_storage_percentile.png"),
        ("composite_drought_index", "composite_drought_index.png"),
    ):
        if column not in monthly or not monthly[column].notna().any():
            continue
        fig, ax = plt.subplots(figsize=(10, 3.5))
        ax.plot(pd.to_datetime(monthly["date"]), monthly[column]); ax.axhline(0, color="black", linewidth=0.6)
        ax.set_ylabel(column); fig.tight_layout(); fig.savefig(output / filename, dpi=130); plt.close(fig)
    zh = output / "drought_index_report_zh.md"
    en = output / "drought_index_report_en.md"
    scales = result.get("scales", DEFAULT_SCALES)
    zh.write_text(
        "# 干旱指标报告\n\n"
        f"- 指标：`{', '.join(result.get('indices', []))}`\n- 时间尺度：`{list(scales)}` 个月\n"
        f"- 基线期：`{result.get('baseline_period')}`\n\n"
        "指标是软件诊断量，不等于当地法定干旱预警等级。短记录或分布拟合失败时采用明确标记的经验分位降级。\n",
        encoding="utf-8",
    )
    en.write_text(
        "# Drought Index Report\n\n"
        f"- indices: `{', '.join(result.get('indices', []))}`\n- scales: `{list(scales)}` months\n"
        f"- baseline: `{result.get('baseline_period')}`\n\n"
        "These are diagnostic indices, not statutory warning levels. Short records and failed fits fall back to an explicitly labeled empirical percentile.\n",
        encoding="utf-8",
    )
    return {"daily": output / "drought_indices_daily.csv", "monthly": output / "drought_indices_monthly.csv", "summary": output / "drought_index_summary.xlsx", "report_zh": zh, "report_en": en}
