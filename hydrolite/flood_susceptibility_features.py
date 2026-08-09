"""Conditioning-factor table construction and quality diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from hydrolite.flood_susceptibility_contracts import default_factor_specs


CONDITIONING_FACTORS = list(default_factor_specs())
CATEGORICAL_FACTORS = [name for name, spec in default_factor_specs().items() if spec.categorical]


def build_factor_table(inventory: Any, factors: Any) -> pd.DataFrame:
    left = pd.DataFrame(inventory).copy(); right = pd.DataFrame(factors).copy()
    if "point_id" not in left or "point_id" not in right: raise ValueError("inventory and factors require point_id")
    return left.merge(right, on="point_id", how="left", validate="one_to_one", suffixes=("", "_factor"))


def detect_missing_factors(data: Any, factors: list[str] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(data); names = list(factors or CONDITIONING_FACTORS)
    return pd.DataFrame([{"factor_id": name, "missing_count": len(frame) if name not in frame else int(frame[name].isna().sum()), "missing_fraction": 1.0 if name not in frame else float(frame[name].isna().mean())} for name in names])


def detect_constant_factors(data: Any, factors: list[str] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(data); names = [name for name in (factors or CONDITIONING_FACTORS) if name in frame]
    return pd.DataFrame([{"factor_id": name, "unique_count": int(frame[name].nunique(dropna=True)), "constant": bool(frame[name].nunique(dropna=True) <= 1)} for name in names])


def calculate_factor_correlation(data: Any, factors: list[str] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(data); names = [name for name in (factors or CONDITIONING_FACTORS) if name in frame and pd.api.types.is_numeric_dtype(frame[name])]
    return frame[names].corr(method="spearman")


def detect_high_correlation(data: Any, threshold: float = 0.80, factors: list[str] | None = None) -> pd.DataFrame:
    correlation = calculate_factor_correlation(data, factors); rows = []
    for i, left in enumerate(correlation.columns):
        for right in correlation.columns[i + 1:]:
            value = correlation.loc[left, right]
            if np.isfinite(value) and abs(value) >= threshold: rows.append({"factor_a": left, "factor_b": right, "correlation": float(value), "threshold": threshold, "action": "flag_only_not_auto_drop"})
    return pd.DataFrame(rows, columns=["factor_a", "factor_b", "correlation", "threshold", "action"])


def validate_factor_coverage(data: Any, factors: list[str] | None = None, maximum_missing_fraction: float = 0.20) -> dict[str, Any]:
    missing = detect_missing_factors(data, factors); constants = detect_constant_factors(data, factors); failed = missing[missing.missing_fraction > maximum_missing_fraction]
    return {"status": "passed" if failed.empty else "failed", "factor_count": len(missing), "missing_failures": failed.factor_id.tolist(), "constant_factors": constants.loc[constants.constant, "factor_id"].tolist(), "high_correlation_action": "flag_only"}


def write_factor_manifest(data: Any, output_dir: str | Path, threshold: float = 0.80) -> dict[str, Path]:
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True); frame = pd.DataFrame(data)
    missing = detect_missing_factors(frame); constants = detect_constant_factors(frame); high = detect_high_correlation(frame, threshold)
    xlsx = root / "factor_qc.xlsx"; manifest = root / "factor_manifest.json"
    with pd.ExcelWriter(xlsx) as writer:
        missing.to_excel(writer, sheet_name="missing", index=False); constants.to_excel(writer, sheet_name="constant", index=False); high.to_excel(writer, sheet_name="high_correlation", index=False); calculate_factor_correlation(frame).to_excel(writer, sheet_name="correlation")
    payload = {**validate_factor_coverage(frame), "correlation_threshold": threshold, "factor_specs": [spec.as_dict() for spec in default_factor_specs().values()]}
    manifest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"xlsx": xlsx, "manifest": manifest}


def recommend_flood_susceptibility_datasets(config: str | None = None) -> dict[str, Any]:
    from hydrolite.gee_catalog.recommend import recommend_datasets
    result = recommend_datasets("flood_susceptibility", config)
    result["recommendations"] = [
        {
            "asset_id": item["asset_id"],
            "suitability_score": item["suitability_score"],
            "matched_characteristics": item["score_components"]["matched_preferred_characteristics"],
            "resolution_m": item.get("resolution_m"),
            "license": item.get("license"),
            "official_url": item.get("official_url"),
            "limitations": item.get("limitations", []),
        }
        for item in result.get("recommendations", [])[:12]
    ]
    result["compute_required"] = False; result["authentication_required_for_catalog"] = False
    return result


def build_synthetic_flood_features(rows: int = 120, seed: int = 7) -> pd.DataFrame:
    """Compatibility fixture for earlier tests; M6 demo uses the versioned 2,400-point dataset."""
    rng = np.random.default_rng(seed); frame = pd.DataFrame({name: rng.normal(size=rows) for name in CONDITIONING_FACTORS if name not in CATEGORICAL_FACTORS})
    for name in CATEGORICAL_FACTORS: frame[name] = rng.integers(0, 4, rows)
    frame["spatial_block"] = np.arange(rows) % 6; frame["x"] = np.arange(rows) % 20; frame["y"] = np.arange(rows) // 20
    score = 1.2 * frame.rainfall_extreme + .8 * frame.surface_runoff - .7 * frame.distance_to_stream + rng.normal(scale=.9, size=rows); frame["flood"] = (score > np.quantile(score, .72)).astype(int)
    return frame


def build_conditioning_features(workspace: Any) -> dict[str, Any]:
    return {"status": "passed", "workspace": str(workspace), "factors": CONDITIONING_FACTORS, "factor_count": len(CONDITIONING_FACTORS), "synthetic_demo": True}
