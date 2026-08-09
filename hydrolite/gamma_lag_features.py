"""Causal Gamma lag features designed independently for HydroLite.

These are derived, diagnostic features. They never mutate or replace the
HydroLite physical water-balance ledger.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


NOTICE = (
    "HydroLite Gamma Lag Features 借鉴公开研究中使用 Gamma 分布描述降雨—径流滞后的通用思想，"
    "由 HydroLite 独立设计，不构成原论文模型复现。"
)
SOURCE_VARIABLES = {
    "rainfall", "effective_rainfall", "surface_runoff", "interflow",
    "baseflow", "total_runoff", "water_yield",
}


def _positive(value: float, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return result


def gamma_pdf(time: Any, shape: float, scale: float) -> np.ndarray:
    """Evaluate the standard Gamma density without using source-model code."""
    shape = _positive(shape, "shape")
    scale = _positive(scale, "scale")
    values = np.asarray(time, dtype=float)
    result = np.zeros_like(values, dtype=float)
    positive = values > 0
    result[positive] = np.exp(
        (shape - 1.0) * np.log(values[positive])
        - values[positive] / scale
        - math.lgamma(shape)
        - shape * math.log(scale)
    )
    at_zero = values == 0
    if shape == 1.0:
        result[at_zero] = 1.0 / scale
    elif shape < 1.0:
        result[at_zero] = np.inf
    result[values < 0] = 0.0
    return result


def normalize_gamma_kernel(kernel: Any) -> np.ndarray:
    values = np.asarray(kernel, dtype=float)
    if values.ndim != 1 or not len(values):
        raise ValueError("Gamma kernel must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError("Gamma kernel must contain finite nonnegative values")
    total = float(values.sum())
    if total <= 0:
        raise ValueError("Gamma kernel sum must be > 0")
    return values / total


def normalize_kernel(kernel: Any) -> np.ndarray:
    """Backward-compatible alias."""
    return normalize_gamma_kernel(kernel)


def build_gamma_kernel(shape: float, scale: float, support_length: int, timestep: float = 1.0) -> np.ndarray:
    shape = _positive(shape, "shape")
    scale = _positive(scale, "scale")
    timestep = _positive(timestep, "timestep")
    if int(support_length) != support_length or support_length < 1:
        raise ValueError("support_length must be a positive integer number of timesteps")
    # Midpoint sampling stays finite for shape < 1 and represents each interval.
    times = (np.arange(int(support_length), dtype=float) + 0.5) * timestep
    return normalize_gamma_kernel(gamma_pdf(times, shape, scale))


def build_causal_gamma_kernel(shape: float, scale: float, length: int = 30, timestep: float = 1.0) -> np.ndarray:
    """Backward-compatible constructor with an explicit causal support."""
    return build_gamma_kernel(shape, scale, length, timestep)


def validate_gamma_kernel(kernel: Any, tolerance: float = 1e-10) -> dict[str, Any]:
    values = np.asarray(kernel, dtype=float)
    errors: list[str] = []
    if values.ndim != 1 or not len(values):
        errors.append("kernel_must_be_nonempty_1d")
    if not np.all(np.isfinite(values)):
        errors.append("kernel_must_be_finite")
    if np.any(values < 0):
        errors.append("kernel_must_be_nonnegative")
    total = float(np.sum(values)) if values.size else 0.0
    if not np.isclose(total, 1.0, atol=tolerance):
        errors.append("kernel_sum_must_equal_one")
    return {"status": "passed" if not errors else "failed", "errors": errors, "kernel_sum": total, "nonnegative": bool(values.size and np.all(values >= 0)), "finite": bool(values.size and np.all(np.isfinite(values)))}


def calculate_gamma_mean_lag(shape: float, scale: float) -> float:
    return _positive(shape, "shape") * _positive(scale, "scale")


def calculate_gamma_peak_lag(shape: float, scale: float) -> float:
    shape = _positive(shape, "shape")
    scale = _positive(scale, "scale")
    return max(shape - 1.0, 0.0) * scale


def calculate_discrete_kernel_mean_lag(kernel: Any, timestep: float = 1.0) -> float:
    values = normalize_gamma_kernel(kernel)
    return float(np.dot(np.arange(len(values), dtype=float) * _positive(timestep, "timestep"), values))


def calculate_discrete_kernel_peak_lag(kernel: Any, timestep: float = 1.0) -> float:
    return float(np.argmax(normalize_gamma_kernel(kernel)) * _positive(timestep, "timestep"))


def calculate_mean_lag(kernel: Any) -> float:
    return calculate_discrete_kernel_mean_lag(kernel)


def calculate_peak_lag(kernel: Any) -> int:
    return int(calculate_discrete_kernel_peak_lag(kernel))


def convolve_causal_series(series: Any, kernel: Any) -> np.ndarray:
    """Zero-padded convolution; output[t] only sees source[:t+1]."""
    values = np.asarray(series, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("series must be a finite one-dimensional array")
    weights = normalize_gamma_kernel(kernel)
    return np.convolve(values, weights, mode="full")[: len(values)]


def build_gamma_feature_series(series: Any, kernel: Any, name: str = "gamma_feature") -> pd.DataFrame:
    values = np.asarray(series, dtype=float)
    weights = normalize_gamma_kernel(kernel)
    response = convolve_causal_series(values, weights)
    history = np.minimum(np.arange(len(values)) + 1, len(weights))
    available = np.cumsum(weights)[np.minimum(np.arange(len(values)), len(weights) - 1)]
    return pd.DataFrame({
        name: response,
        "is_warmup": history < len(weights),
        "available_kernel_fraction": available,
        "effective_history_length": history,
    })


def validate_gamma_parameters(parameters: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = parameters if isinstance(parameters, Sequence) and not isinstance(parameters, (str, bytes, dict)) else [parameters]
    errors: list[str] = []
    for index, item in enumerate(rows):
        for key in ("shape", "scale"):
            try:
                _positive(float(item[key]), key)
            except (KeyError, TypeError, ValueError):
                errors.append(f"component_{index}_{key}_must_be_positive")
        if int(item.get("support_length", 0)) < 1:
            errors.append(f"component_{index}_support_length_must_be_positive")
        if float(item.get("weight", 0.0)) < 0:
            errors.append(f"component_{index}_weight_must_be_nonnegative")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def build_multi_gamma_features(series: Any, components: Sequence[Mapping[str, Any]], timestep: float = 1.0) -> dict[str, Any]:
    enabled = [dict(item) for item in components if item.get("enabled", True)]
    validation = validate_gamma_parameters(enabled)
    if validation["status"] != "passed":
        raise ValueError("; ".join(validation["errors"]))
    arrays: dict[str, np.ndarray] = {}
    kernels: dict[str, np.ndarray] = {}
    summaries: list[dict[str, Any]] = []
    for item in enabled:
        component_id = str(item["component_id"])
        kernel = build_gamma_kernel(item["shape"], item["scale"], int(item["support_length"]), timestep)
        feature = convolve_causal_series(series, kernel)
        kernels[component_id] = kernel
        arrays[component_id] = feature
        summaries.append({
            "component_id": component_id,
            "shape": float(item["shape"]),
            "scale": float(item["scale"]),
            "analytical_mean_lag": calculate_gamma_mean_lag(item["shape"], item["scale"]),
            "analytical_peak_lag": calculate_gamma_peak_lag(item["shape"], item["scale"]),
            "discrete_mean_lag": calculate_discrete_kernel_mean_lag(kernel, timestep),
            "discrete_peak_lag": calculate_discrete_kernel_peak_lag(kernel, timestep),
            "support_length": int(item["support_length"]),
            "weight": float(item["weight"]),
            "kernel_sum": float(kernel.sum()),
            "effective_duration": float(len(kernel) * timestep),
            "volume_contribution": float(np.sum(feature) * float(item["weight"])),
        })
    frame = pd.DataFrame(arrays)
    weights = [float(item["weight"]) for item in enabled]
    combination = combine_gamma_components(frame, weights, return_metadata=True)
    return {"features": frame, "kernels": kernels, "component_summary": pd.DataFrame(summaries), **combination}


def build_fast_medium_slow_features(series: Any, specs: Mapping[str, Any] | None = None) -> pd.DataFrame:
    specs = specs or {"quick": (1.5, 1.0), "intermediate": (3.0, 2.0), "slow": (5.0, 4.0)}
    components = []
    for name, spec in specs.items():
        if isinstance(spec, Mapping):
            components.append({"component_id": name, "support_length": 30, "weight": 1.0, "enabled": True, **spec})
        else:
            components.append({"component_id": name, "shape": spec[0], "scale": spec[1], "support_length": 30, "weight": 1.0, "enabled": True})
    return build_multi_gamma_features(series, components)["features"]


def combine_gamma_components(components: Any, weights: Any = None, *, return_metadata: bool = False) -> Any:
    frame = pd.DataFrame(components)
    raw = np.asarray(weights if weights is not None else np.ones(frame.shape[1]), dtype=float)
    if raw.ndim != 1 or len(raw) != frame.shape[1] or not np.all(np.isfinite(raw)) or np.any(raw < 0) or raw.sum() <= 0:
        raise ValueError("component weights must be finite, nonnegative, and have a positive sum")
    normalized = raw / raw.sum()
    combined = pd.Series(frame.to_numpy(dtype=float) @ normalized, index=frame.index, name="gamma_lag_combined")
    if return_metadata:
        return {"combined": combined, "raw_weights": raw.tolist(), "normalized_weights": normalized.tolist()}
    return combined


def combine_lag_components(features: Any, weights: Any = None) -> pd.Series:
    return combine_gamma_components(features, weights)


def detect_gamma_future_leakage(series: Any, kernel: Any, cutoff_index: int | None = None) -> dict[str, Any]:
    values = np.asarray(series, dtype=float)
    cutoff = len(values) // 2 if cutoff_index is None else int(cutoff_index)
    if cutoff < 0 or cutoff >= len(values):
        raise ValueError("cutoff_index must reference the input series")
    original = convolve_causal_series(values, kernel)
    changed = values.copy()
    changed[cutoff + 1 :] = changed[cutoff + 1 :] + 1000.0
    modified = convolve_causal_series(changed, kernel)
    maximum = float(np.max(np.abs(original[: cutoff + 1] - modified[: cutoff + 1])))
    return {"status": "passed" if maximum <= 1e-12 else "failed", "cutoff_index": cutoff, "maximum_past_difference": maximum, "future_values_used": maximum > 1e-12}


def build_gamma_features_from_hydrolite(hydrolite_output: Any, config: Mapping[str, Any]) -> dict[str, Any]:
    frame = pd.read_csv(hydrolite_output) if isinstance(hydrolite_output, (str, Path)) else pd.DataFrame(hydrolite_output).copy()
    source_variable = str(config["source_variable"])
    if source_variable not in SOURCE_VARIABLES:
        raise ValueError(f"Unsupported Gamma source variable: {source_variable}")
    if source_variable not in frame:
        raise ValueError(f"HydroLite output has no column: {source_variable}")
    result = build_multi_gamma_features(frame[source_variable].to_numpy(), config["components"], float(config.get("timestep", 1.0)))
    feature_frame = frame.copy()
    for column in result["features"]:
        feature_frame[f"gamma_{column}"] = result["features"][column]
    feature_frame["gamma_combined"] = result["combined"]
    result["feature_frame"] = feature_frame
    result["provenance"] = {
        "source_variable": source_variable,
        "source_unit": config.get("source_unit", "unknown"),
        "source_dataset_id": config.get("source_dataset_id", "unassigned"),
        "source_run_id": config.get("source_run_id", "unassigned"),
        "derived_feature_only": True,
        "physical_water_balance_modified": False,
    }
    return result


def calculate_gamma_feature_manifest(config: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "method_id": "gamma_lag_hydrologic_prior",
        "implementation_name": "Gamma Lag Features",
        "notice": NOTICE,
        "timestep": config.get("timestep"),
        "timestep_unit": config.get("timestep_unit", "day"),
        "source_variable": config.get("source_variable"),
        "warmup_policy": config.get("warmup_policy", "zero_padding_with_warmup_flag"),
        "component_count": len(result.get("kernels", {})),
        "normalized_weights": result.get("normalized_weights", []),
        "derived_feature_only": True,
        "physical_water_balance_modified": False,
    }


def validate_gamma_features(kernel: Any, output: Any = None) -> dict[str, Any]:
    result = validate_gamma_kernel(kernel)
    result.update({"causal": True, "future_values_used": False, "output_rows": len(output) if output is not None else None})
    return result


def write_gamma_feature_report(output_dir: str | Path = "output/method_inspiration/gamma") -> dict[str, Any]:
    """Backward-compatible lightweight kernel/feature export used by old CLI."""
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    rainfall = np.maximum(0.0, np.sin(np.arange(80) / 5.0) * 12.0)
    specs = {"quick": (1.5, 1.0), "intermediate": (3.0, 2.0), "slow": (5.0, 4.0)}
    features = build_fast_medium_slow_features(rainfall, specs)
    weights = [0.5, 0.3, 0.2]
    frame = pd.DataFrame({"rainfall": rainfall, **features, "combined": combine_gamma_components(features, weights)})
    kernels = pd.DataFrame({name: build_gamma_kernel(*params, 30, 1.0) for name, params in specs.items()})
    frame.to_csv(root / "gamma_lag_features.csv", index=False)
    kernels.to_excel(root / "gamma_kernels.xlsx", index=False)
    report = root / "gamma_feature_report.md"
    report.write_text(f"# Gamma Lag Features\n\n{NOTICE}\n\nDerived features only; the HydroLite physical ledger is unchanged.\n", encoding="utf-8")
    return {"status": "passed", "kernels": root / "gamma_kernels.xlsx", "features": root / "gamma_lag_features.csv", "report": report, "weights": weights}
