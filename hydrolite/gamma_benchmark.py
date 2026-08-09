"""Dependency-light baselines and sample-efficiency checks for Gamma features."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hydrolite.gamma_lag_features import build_gamma_kernel, convolve_causal_series
from hydrolite.continuous_benchmarks import build_rainfall_linear_reservoir_benchmark
from hydrolite.gamma_validation import (
    DEFAULT_DEMO_ROOT,
    DEFAULT_OUTPUT,
    _load_demo,
    _safe_root,
    default_components,
    fit_multi_gamma,
    fit_single_gamma,
    response_metrics,
)


def _fit_scale(feature: np.ndarray, observed: np.ndarray) -> float:
    denominator = float(np.dot(feature, feature))
    return max(0.0, float(np.dot(feature, observed) / denominator)) if denominator else 0.0


def raw_current_input(source: Any, observed_train: Any) -> tuple[np.ndarray, int]:
    x = np.asarray(source, dtype=float); y = np.asarray(observed_train, dtype=float)
    coefficient = _fit_scale(x[: len(y)], y)
    return x * coefficient, 1


def rolling_sum(source: Any, observed_train: Any, windows: tuple[int, ...] = (2, 3, 5, 7, 10)) -> tuple[np.ndarray, int, int]:
    x = np.asarray(source, dtype=float); y = np.asarray(observed_train, dtype=float); best = None
    for window in windows:
        feature = pd.Series(x).rolling(window, min_periods=1).sum().to_numpy()
        coefficient = _fit_scale(feature[: len(y)], y)
        error = float(np.mean((feature[: len(y)] * coefficient - y) ** 2))
        if best is None or error < best[0]: best = (error, feature * coefficient, window)
    assert best is not None
    return best[1], 2, best[2]


def exponential_decay(source: Any, observed_train: Any, alphas: tuple[float, ...] = (0.15, 0.25, 0.4, 0.6, 0.8)) -> tuple[np.ndarray, int, float]:
    x = np.asarray(source, dtype=float); y = np.asarray(observed_train, dtype=float); best = None
    for alpha in alphas:
        state = 0.0; feature = []
        for value in x:
            state = alpha * value + (1.0 - alpha) * state; feature.append(state)
        values = np.asarray(feature); coefficient = _fit_scale(values[: len(y)], y)
        error = float(np.mean((values[: len(y)] * coefficient - y) ** 2))
        if best is None or error < best[0]: best = (error, values * coefficient, alpha)
    assert best is not None
    return best[1], 2, best[2]


def linear_reservoir(source: Any, observed_train: Any, storage_constants: tuple[float, ...] = (1.0, 2.0, 3.0, 5.0, 8.0)) -> tuple[np.ndarray, int, float]:
    """Reuse the same first-order reservoir recurrence used by HydroLite baselines."""
    x = np.asarray(source, dtype=float); y = np.asarray(observed_train, dtype=float); best = None
    forcing = pd.DataFrame({"date": pd.date_range("2000-01-01", periods=len(x), freq="D"), "precipitation_mm": x})
    for storage in storage_constants:
        values = build_rainfall_linear_reservoir_benchmark(forcing, area_km2=1.0, coefficient=1.0, k_days=storage).to_numpy()
        coefficient = _fit_scale(values[: len(y)], y)
        error = float(np.mean((values[: len(y)] * coefficient - y) ** 2))
        if best is None or error < best[0]: best = (error, values * coefficient, storage)
    assert best is not None
    return best[1], 2, best[2]


def _metric_row(model: str, observed: np.ndarray, predicted: np.ndarray, parameter_count: int, compute_time: float, warmup_steps: int) -> dict[str, Any]:
    return {"model": model, **response_metrics(observed, predicted), "parameter_count": parameter_count, "compute_time_seconds": compute_time, "warmup_steps": warmup_steps}


def run_gamma_benchmark(output_dir: str | Path = DEFAULT_OUTPUT, demo_root: str | Path = DEFAULT_DEMO_ROOT) -> dict[str, Any]:
    source, response, truth = _load_demo("multi_kernel", demo_root)
    observed = response["clean_response"].to_numpy(dtype=float); split = int(len(source) * 0.70); test = slice(split, len(source))
    rows = []; predictions: dict[str, np.ndarray] = {}
    for name, builder in (("Raw", raw_current_input), ("Rolling", rolling_sum), ("Exponential", exponential_decay), ("Linear Reservoir", linear_reservoir)):
        started = time.perf_counter(); result = builder(source, observed[:split]); elapsed = time.perf_counter() - started
        prediction, count = result[0], result[1]; predictions[name] = prediction
        rows.append(_metric_row(name, observed[test], prediction[test], count, elapsed, 0))
    started = time.perf_counter(); single = fit_single_gamma(source[:split], observed[:split], support_length=40)
    single_prediction = convolve_causal_series(source, build_gamma_kernel(single["shape"], single["scale"], 40, 1.0)) * single["runoff_coefficient"]
    rows.append(_metric_row("Gamma Single", observed[test], single_prediction[test], 3, time.perf_counter() - started, 40)); predictions["Gamma Single"] = single_prediction
    started = time.perf_counter(); multi = fit_multi_gamma(source[:split], observed[:split], truth["components"], max_nfev=550)
    multi_prediction = np.zeros_like(source)
    for item in multi["components"]:
        multi_prediction += item["weight"] * convolve_causal_series(source, build_gamma_kernel(item["shape"], item["scale"], item["support_length"], 1.0))
    rows.append(_metric_row("Gamma Multi", observed[test], multi_prediction[test], 9, time.perf_counter() - started, max(item["support_length"] for item in multi["components"]))); predictions["Gamma Multi"] = multi_prediction
    metrics = pd.DataFrame(rows)
    gamma_nse = float(metrics.loc[metrics.model == "Gamma Multi", "NSE"].iloc[0]); baselines = metrics[metrics.model.isin(["Raw", "Rolling", "Exponential", "Linear Reservoir"])]
    comparisons = {f"better_than_{row.model.lower().replace(' ', '_')}": gamma_nse > float(row.NSE) for row in baselines.itertuples()}
    synthetic_value_added = "demonstrated" if all(comparisons.values()) else "not_demonstrated"
    root = _safe_root(output_dir); folder = root / "benchmark"; folder.mkdir(exist_ok=True)
    metrics.to_excel(folder / "benchmark_metrics.xlsx", index=False)
    pd.DataFrame([{**comparisons, "synthetic_value_added": synthetic_value_added, "real_data_value_added": "not_tested", "test_start_index": split, "temporal_shuffle": False}]).to_excel(folder / "benchmark_summary.xlsx", index=False)
    fig, ax = plt.subplots(figsize=(8, 4)); ax.bar(metrics.model, metrics.NSE); ax.set_ylabel("NSE"); ax.tick_params(axis="x", rotation=30); ax.set_title("Independent fixed-window benchmark"); fig.tight_layout(); fig.savefig(root / "benchmark_comparison.png", dpi=150); plt.close(fig)
    return {"status": "passed", "metrics": metrics, "comparisons": comparisons, "synthetic_value_added": synthetic_value_added, "real_data_value_added": "not_tested", "test_start_index": split, "output": folder / "benchmark_metrics.xlsx"}


def run_sample_efficiency(output_dir: str | Path = DEFAULT_OUTPUT, demo_root: str | Path = DEFAULT_DEMO_ROOT) -> dict[str, Any]:
    source, response, truth = _load_demo("single_kernel", demo_root)
    observed = response["clean_response"].to_numpy(dtype=float); train_end = int(len(source) * 0.70); test = slice(train_end, len(source)); rows = []
    full_fit = None
    for fraction in (1.0, 0.5, 0.25, 0.10):
        count = max(1, int(train_end * fraction))
        if count < 20:
            rows.append({"training_fraction": fraction, "training_count": count, "status": "insufficient_sample", "NSE": np.nan, "KGE": np.nan, "PBIAS": np.nan, "shape": np.nan, "scale": np.nan, "runoff_coefficient": np.nan, "test_start_index": train_end, "temporal_shuffle": False}); continue
        fit = fit_single_gamma(source[:count], observed[:count], support_length=truth["single"]["support_length"])
        prediction = convolve_causal_series(source, build_gamma_kernel(fit["shape"], fit["scale"], truth["single"]["support_length"], 1.0)) * fit["runoff_coefficient"]
        metrics = response_metrics(observed[test], prediction[test]); row = {"training_fraction": fraction, "training_count": count, "status": "passed", **metrics, "shape": fit["shape"], "scale": fit["scale"], "runoff_coefficient": fit["runoff_coefficient"], "test_start_index": train_end, "temporal_shuffle": False}; rows.append(row)
        if fraction == 1.0: full_fit = row
    table = pd.DataFrame(rows); valid = table[table.status == "passed"].copy()
    reference = valid.iloc[0] if len(valid) else None
    stability = pd.DataFrame([{ "training_fraction": row.training_fraction, "shape_relative_to_full": float(abs(row.shape - reference["shape"]) / reference["shape"]) if reference is not None else np.nan, "scale_relative_to_full": float(abs(row.scale - reference["scale"]) / reference["scale"]) if reference is not None else np.nan, "status": "stable" if reference is not None and abs(row.shape-reference["shape"])/reference["shape"] <= .25 and abs(row.scale-reference["scale"])/reference["scale"] <= .25 else "sensitive"} for row in valid.itertuples()])
    root = _safe_root(output_dir); folder = root / "sample_efficiency"; folder.mkdir(exist_ok=True)
    table.to_excel(folder / "sample_efficiency_metrics.xlsx", index=False); stability.to_excel(folder / "parameter_stability.xlsx", index=False)
    fig, ax = plt.subplots(figsize=(7, 3.5)); plotted = table.dropna(subset=["NSE"]); ax.plot(plotted.training_fraction * 100, plotted.NSE, marker="o"); ax.set(xlabel="Training window (%)", ylabel="Test NSE", title="Gamma sample-length sensitivity"); ax.invert_xaxis(); fig.tight_layout(); fig.savefig(root / "sample_efficiency.png", dpi=150); plt.close(fig)
    return {"status": "passed", "metrics": table, "stability": stability, "fixed_test_start": train_end, "temporal_shuffle": False, "output": folder / "sample_efficiency_metrics.xlsx"}
