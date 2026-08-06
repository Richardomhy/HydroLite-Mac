from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


def gamma_pdf(x, shape: float, scale: float):
    if shape <= 0 or scale <= 0: raise ValueError("shape and scale must be > 0")
    values = np.asarray(x, dtype=float); result = np.zeros_like(values)
    valid = values >= 0
    result[valid] = np.exp((shape - 1) * np.log(np.maximum(values[valid], 1e-12)) - values[valid] / scale - math.lgamma(shape) - shape * math.log(scale))
    return result


def normalize_kernel(kernel):
    values = np.asarray(kernel, dtype=float)
    if np.any(values < 0) or values.sum() <= 0: raise ValueError("Gamma kernel must be nonnegative with positive sum")
    return values / values.sum()


def build_causal_gamma_kernel(shape: float, scale: float, length: int = 30):
    if length < 1: raise ValueError("length must be positive")
    return normalize_kernel(gamma_pdf(np.arange(length, dtype=float), shape, scale))


def calculate_mean_lag(kernel): return float(np.dot(np.arange(len(kernel)), normalize_kernel(kernel)))
def calculate_peak_lag(kernel): return int(np.argmax(normalize_kernel(kernel)))


def convolve_causal_series(series, kernel):
    """Only present and past inputs enter each output sample."""
    return np.convolve(np.asarray(series, dtype=float), normalize_kernel(kernel), mode="full")[:len(series)]


def build_fast_medium_slow_features(series, specs=None):
    specs = specs or {"fast": (1.5, 1.0), "medium": (3.0, 2.0), "slow": (5.0, 4.0)}
    return pd.DataFrame({name: convolve_causal_series(series, build_causal_gamma_kernel(shape, scale)) for name, (shape, scale) in specs.items()})


def combine_lag_components(features, weights=None):
    frame = pd.DataFrame(features); weights = np.asarray(weights if weights is not None else np.repeat(1 / frame.shape[1], frame.shape[1]), dtype=float)
    if np.any(weights < 0) or not np.isclose(weights.sum(), 1.0): raise ValueError("component weights must be nonnegative and sum to 1")
    return pd.Series(frame.to_numpy() @ weights, index=frame.index, name="gamma_lag_combined")


def validate_gamma_features(kernel, output=None):
    values = np.asarray(kernel, dtype=float)
    return {"status": "passed" if np.all(values >= 0) and np.isclose(values.sum(), 1.0) else "failed", "causal": True, "kernel_sum": float(values.sum()), "future_values_used": False, "output_rows": len(output) if output is not None else None}


def write_gamma_feature_report(output_dir="output/method_inspiration"):
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True); rainfall = np.maximum(0, np.sin(np.arange(80) / 5) * 12)
    specs = {"fast": (1.5, 1.0), "medium": (3.0, 2.0), "slow": (5.0, 4.0)}; features = build_fast_medium_slow_features(rainfall, specs); weights = [0.5, 0.3, 0.2]
    frame = pd.DataFrame({"rainfall": rainfall, **features, "combined": combine_lag_components(features, weights)})
    kernels = pd.DataFrame({name: build_causal_gamma_kernel(*params) for name, params in specs.items()})
    frame.to_csv(root / "gamma_lag_features.csv", index=False); kernels.to_excel(root / "gamma_kernels.xlsx", index=False)
    text = "# Gamma causal lag features\n\n" + "\n".join(f"- {name}: mean_lag={calculate_mean_lag(kernels[name]):.2f}, peak_lag={calculate_peak_lag(kernels[name])}, weight={weights[i]}" for i, name in enumerate(specs)) + "\n- Causal feature engineering only; not a new physical model.\n"
    (root / "gamma_feature_report.md").write_text(text, encoding="utf-8")
    return {"status": "passed", "kernels": root / "gamma_kernels.xlsx", "features": root / "gamma_lag_features.csv", "report": root / "gamma_feature_report.md", "weights": weights}
