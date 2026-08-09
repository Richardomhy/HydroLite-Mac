"""Strictly causal trend and seasonal features for forecast issue times."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


def _series(values: Any, timestamps: Any | None = None) -> pd.Series:
    if isinstance(values, pd.Series) and timestamps is None:
        result = values.astype(float).copy()
        if not isinstance(result.index, pd.DatetimeIndex): result.index = pd.RangeIndex(len(result))
        return result
    result = pd.Series(values, dtype=float)
    if timestamps is not None: result.index = pd.to_datetime(timestamps)
    return result


def build_lag_features(values: Any, lags: Iterable[int] = (1, 3, 7), timestamps: Any | None = None) -> pd.DataFrame:
    series = _series(values, timestamps); return pd.DataFrame({f"lag_{int(lag)}": series.shift(int(lag)) for lag in lags}, index=series.index)


def build_rolling_features(values: Any, windows: Iterable[int] = (3, 7, 14), timestamps: Any | None = None, *, centered: bool = False, analysis_only: bool = False) -> pd.DataFrame:
    if centered and not analysis_only: raise ValueError("centered_rolling_forecast_blocked: centered windows are analysis_only")
    series = _series(values, timestamps); result = pd.DataFrame(index=series.index)
    for window in windows:
        rolling = series.rolling(int(window), min_periods=1, center=centered)
        result[f"rolling_mean_{window}"] = rolling.mean(); result[f"rolling_median_{window}"] = rolling.median(); result[f"rolling_sum_{window}"] = rolling.sum(); result[f"rolling_min_{window}"] = rolling.min(); result[f"rolling_max_{window}"] = rolling.max(); result[f"rolling_std_{window}"] = rolling.std(); result[f"rolling_cv_{window}"] = result[f"rolling_std_{window}"] / result[f"rolling_mean_{window}"].replace(0, np.nan)
    result.attrs.update({"centered": centered, "analysis_only": analysis_only, "causal": not centered})
    return result


def calculate_robust_local_trend(values: Any, window: int = 7, timestamps: Any | None = None) -> pd.Series:
    series = _series(values, timestamps)
    def median_slope(sample: np.ndarray) -> float:
        x = np.arange(len(sample)); slopes = [(sample[j] - sample[i]) / (j - i) for i in range(len(sample)) for j in range(i + 1, len(sample)) if np.isfinite(sample[i]) and np.isfinite(sample[j])]
        return float(np.median(slopes)) if slopes else np.nan
    return series.rolling(window, min_periods=2).apply(median_slope, raw=True).rename("robust_local_slope")


def calculate_robust_trend(values: Any, window: int = 7) -> pd.Series:
    return calculate_robust_local_trend(values, window)


def calculate_seasonal_baseline(values: Any, timestamps: Any, fit_start: Any, fit_end: Any, method: str = "day_of_year") -> tuple[pd.Series, dict[str, Any]]:
    series = _series(values, timestamps); start, end = pd.Timestamp(fit_start), pd.Timestamp(fit_end)
    if end < start: raise ValueError("seasonal baseline fit_end must be on or after fit_start")
    fit = series.loc[(series.index >= start) & (series.index <= end)]
    if fit.empty: raise ValueError("seasonal baseline training period is empty")
    if method not in {"day_of_year", "month"}: raise ValueError("seasonal baseline method must be day_of_year or month")
    fit_key = fit.index.dayofyear if method == "day_of_year" else fit.index.month; full_key = series.index.dayofyear if method == "day_of_year" else series.index.month
    lookup = fit.groupby(fit_key).mean(); fallback = float(fit.mean()); baseline = pd.Series([lookup.get(key, fallback) for key in full_key], index=series.index, name="seasonal_baseline")
    metadata = {"fit_start": start.isoformat(), "fit_end": end.isoformat(), "sample_count": int(fit.notna().sum()), "baseline_method": method, "validation_or_test_used": False}
    baseline.attrs.update(metadata); return baseline, metadata


def calculate_seasonal_anomaly(values: Any, baseline: Any, timestamps: Any | None = None) -> pd.Series:
    series = _series(values, timestamps); base = pd.Series(baseline, index=series.index, dtype=float); return (series - base).rename("seasonal_anomaly")


def calculate_recent_volatility(values: Any, window: int = 7, timestamps: Any | None = None) -> pd.Series:
    return _series(values, timestamps).rolling(window, min_periods=2).std().rename("recent_volatility")


def calculate_change_features(values: Any, window: int = 7, timestamps: Any | None = None) -> pd.DataFrame:
    series = _series(values, timestamps); first = series.diff(); second = first.diff(); threshold = first.abs().rolling(window, min_periods=2).median() * 2
    return pd.DataFrame({"first_difference": first, "second_difference": second, "change_magnitude": first.abs(), "recent_acceleration": second, "change_point_indicator": (first.abs() > threshold).astype(int)}, index=series.index)


def build_causal_trend_features(values: Any, timestamps: Any, *, lags: Iterable[int] = (1, 3, 7), windows: Iterable[int] = (3, 7, 14), issue_time: Any | None = None, fit_start: Any | None = None, fit_end: Any | None = None, seasonal_method: str = "day_of_year") -> tuple[pd.DataFrame, dict[str, Any]]:
    series = _series(values, timestamps); cutoff = pd.Timestamp(issue_time) if issue_time is not None else series.index.max()
    if fit_start is None: fit_start = series.index.min()
    if fit_end is None: fit_end = min(cutoff, series.index[int(max(0, len(series) * 0.6 - 1))])
    baseline, baseline_metadata = calculate_seasonal_baseline(series, series.index, fit_start, fit_end, seasonal_method)
    parts = [build_lag_features(series, lags), build_rolling_features(series, windows), calculate_robust_local_trend(series).to_frame(), calculate_change_features(series), calculate_recent_volatility(series).to_frame()]
    frame = pd.concat(parts, axis=1); frame["exponential_moving_mean"] = series.ewm(span=7, adjust=False).mean(); frame["seasonal_baseline"] = baseline; frame["seasonal_anomaly"] = series - baseline; frame["recent_percentile"] = series.rolling(30, min_periods=2).rank(pct=True); frame["missingness_indicator"] = series.isna().astype(int)
    frame = frame.loc[frame.index <= cutoff]
    metadata = {"issue_time": cutoff.isoformat(), "causal": True, "centered_rolling": False, "analysis_only": False, "seasonal_baseline": baseline_metadata, "feature_count": len(frame.columns)}
    frame.attrs.update(metadata); return frame, metadata


def extract_trend_features(series: Any, window: int = 7) -> pd.DataFrame:
    values = _series(series); result = pd.concat([calculate_robust_local_trend(values, window).rename("rolling_trend"), values.rolling(window, min_periods=1).median().rename("moving_median"), calculate_change_features(values, window), calculate_recent_volatility(values, window), values.ewm(span=window, adjust=False).mean().rename("exponential_trend")], axis=1); return result


def extract_seasonal_features(series: Any, timestamps: Any, fit_start: Any | None = None, fit_end: Any | None = None) -> pd.DataFrame:
    dates = pd.to_datetime(timestamps); start = dates.min() if fit_start is None else pd.Timestamp(fit_start); end = dates.max() if fit_end is None else pd.Timestamp(fit_end); baseline, _ = calculate_seasonal_baseline(series, dates, start, end, "month"); values = _series(series, dates); return pd.DataFrame({"seasonal_baseline": baseline, "anomaly": values - baseline, "month": dates.month}, index=dates)


def extract_anomaly_features(series: Any, timestamps: Any) -> pd.DataFrame:
    return extract_seasonal_features(series, timestamps)[["anomaly"]]


def build_causal_temporal_context(series: Any, timestamps: Any, lags: Iterable[int] = (1, 3, 7), issue_time: Any | None = None) -> pd.DataFrame:
    frame, _ = build_causal_trend_features(series, timestamps, lags=lags, issue_time=issue_time); return frame


def detect_temporal_feature_leakage(features: Any, issue_time: Any) -> dict[str, Any]:
    frame = pd.DataFrame(features); index = pd.to_datetime(frame.index); leaked = [value.isoformat() for value in index[index > pd.Timestamp(issue_time)]]
    centered = bool(getattr(features, "attrs", {}).get("centered", False) or getattr(features, "attrs", {}).get("centered_rolling", False))
    return {"status": "passed" if not leaked and not centered else "future_context_leakage_blocked", "issue_time": pd.Timestamp(issue_time).isoformat(), "future_rows": leaked, "centered_rolling": centered}


def detect_future_leakage(features: Any, issue_time: Any) -> dict[str, Any]:
    return detect_temporal_feature_leakage(features, issue_time)


def validate_trend_feature_causality(features: Any, issue_time: Any, baseline_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    temporal = detect_temporal_feature_leakage(features, issue_time); baseline = baseline_metadata or getattr(features, "attrs", {}).get("seasonal_baseline", {})
    seasonal_leakage = bool(baseline.get("validation_or_test_used")) or (baseline.get("fit_end") and pd.Timestamp(baseline["fit_end"]) > pd.Timestamp(issue_time))
    return {"status": "passed" if temporal["status"] == "passed" and not seasonal_leakage else "failed", "temporal": temporal, "seasonal_baseline_leakage": seasonal_leakage, "centered_rolling_forecast_gate": "passed" if not temporal["centered_rolling"] else "blocked"}


def validate_feature_causality(features: Any, issue_time: Any) -> dict[str, Any]:
    return validate_trend_feature_causality(features, issue_time)


def write_trend_feature_report(output_dir: str | Path = "output/method_inspiration/graph_trend/features") -> dict[str, Any]:
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True); dates = pd.date_range("2020-01-01", periods=730, freq="D"); values = 4 + np.sin(np.arange(730) * 2 * np.pi / 365) + np.arange(730) * 0.002
    issue_time = dates[620]; frame, metadata = build_causal_trend_features(values, dates, issue_time=issue_time, fit_start=dates[0], fit_end=dates[364]); path = root / "trend_features.csv"; frame.reset_index(names="timestamp").to_csv(path, index=False)
    validation = validate_trend_feature_causality(frame, issue_time, metadata["seasonal_baseline"]); (root / "trend_feature_manifest.json").write_text(json.dumps({**metadata, "validation": validation}, indent=2, ensure_ascii=False), encoding="utf-8")
    report = root / "trend_feature_report.md"; report.write_text("# Causal trend features\n\nForecast features use backward windows and timestamps at or before issue time. Seasonal baselines are fit on the training period only. Centered windows are blocked outside analysis-only mode.\n", encoding="utf-8")
    return {"status": validation["status"], "features": path, "report": report, "metadata": metadata, "validation": validation}
