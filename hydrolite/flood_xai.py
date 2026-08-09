"""Association-oriented XAI with dependency-light fallbacks."""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score


XAI_NOTICE = "Feature importance and SHAP-like contributions are associations, not causal effects."


def permutation_importance(model: Any, features: Any, labels: Any, factor_names: Sequence[str], seed: int = 7) -> pd.DataFrame:
    frame = pd.DataFrame(features).copy(); y = np.asarray(labels, dtype=int); rng = np.random.default_rng(seed); base = average_precision_score(y, model.predict_proba(frame[list(factor_names)])); rows = []
    for factor in factor_names:
        shuffled = frame[list(factor_names)].copy(); shuffled[factor] = rng.permutation(shuffled[factor].to_numpy()); score = average_precision_score(y, model.predict_proba(shuffled)); rows.append({"factor_id": factor, "importance": float(base - score), "metric": "PR_AUC_drop", "interpretation": "association_not_causal_effect"})
    return pd.DataFrame(rows).sort_values(["importance", "factor_id"], ascending=[False, True]).reset_index(drop=True)


def partial_dependence(model: Any, features: Any, factor_names: Sequence[str], maximum_factors: int = 5) -> pd.DataFrame:
    frame = pd.DataFrame(features).copy(); rows = []
    for factor in [name for name in factor_names if pd.api.types.is_numeric_dtype(frame[name])][:maximum_factors]:
        for value in np.unique(np.quantile(frame[factor].dropna(), np.linspace(.05, .95, 9))):
            changed = frame[list(factor_names)].copy(); changed[factor] = value; rows.append({"factor_id": factor, "factor_value": float(value), "mean_probability": float(model.predict_proba(changed).mean()), "interpretation": "model_response_not_causal_effect"})
    return pd.DataFrame(rows)


def local_perturbation_explanation(model: Any, row: Any, reference: Any, factor_names: Sequence[str], *, case_type: str, block_id: str, uncertainty: float = np.nan) -> dict[str, Any]:
    sample = pd.DataFrame([dict(row)])[list(factor_names)]; ref = pd.DataFrame([dict(reference)])[list(factor_names)]; prediction = float(model.predict_proba(sample)[0]); base = float(model.predict_proba(ref)[0]); contributions = []
    for factor in factor_names:
        perturbed = sample.copy(); perturbed[factor] = ref.iloc[0][factor]; changed = float(model.predict_proba(perturbed)[0]); contributions.append((factor, prediction - changed))
    positive = sorted((item for item in contributions if item[1] >= 0), key=lambda item: item[1], reverse=True)[:5]; negative = sorted((item for item in contributions if item[1] < 0), key=lambda item: item[1])[:5]
    return {"case_type": case_type, "prediction": prediction, "base_probability": base, "top_positive_factors": "; ".join(f"{name}:{value:.4f}" for name, value in positive), "top_negative_factors": "; ".join(f"{name}:{value:.4f}" for name, value in negative), "uncertainty": uncertainty, "block_id": str(block_id), "interpretation": "local_association_not_causal_effect"}


def select_local_explanation_cases(data: Any, probability_column: str, threshold: float) -> dict[str, pd.Series]:
    frame = pd.DataFrame(data).copy(); prediction = frame[probability_column] >= threshold
    masks = {"true_positive": (frame.label == 1) & prediction, "true_negative": (frame.label == 0) & ~prediction, "false_positive": (frame.label == 0) & prediction, "false_negative": (frame.label == 1) & ~prediction}
    return {name: frame[mask].iloc[0] for name, mask in masks.items() if mask.any()}


def feature_importance_stability(importances: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.DataFrame(importances); summary = frame.groupby("factor_id", as_index=False).importance.agg(["mean", "std", "count"]).reset_index().rename(columns={"mean": "importance_mean", "std": "importance_std", "count": "replicate_count"})
    normalized_variance = float(summary.importance_std.fillna(0).mean() / max(summary.importance_mean.abs().mean(), 1e-9)); status = "stable" if normalized_variance <= .25 else "moderately_stable" if normalized_variance <= .60 else "unstable"
    return summary.sort_values("importance_mean", ascending=False), {"status": status, "normalized_importance_variability": normalized_variance}


spatial_importance_stability = feature_importance_stability


def xai_status() -> dict[str, Any]:
    return {"status": "shap_available" if find_spec("shap") else "shap_optional_dependency_missing", "fallbacks": ["permutation_importance", "partial_dependence", "local_perturbation_explanation"], "causal_interpretation_allowed": False, "notice": XAI_NOTICE}


def validate_xai_causality_claim(text: str) -> dict[str, Any]:
    lowered = text.lower()
    causal_terms = ("causal effect", "causes ", "caused ", "cause of", "因果效应", "导致洪水", "引起洪水")
    disclaimers = ("not causal", "non-causal", "association", "非因果", "不表示因果")
    bad = any(term in lowered for term in causal_terms) and not any(term in lowered for term in disclaimers)
    return {"status": "passed" if not bad else "failed", "causal_claim_detected": bad, "required_interpretation": "association_not_causal_effect"}
