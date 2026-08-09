"""Classification, calibration, block-stability, and value-added metrics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, balanced_accuracy_score, brier_score_loss,
    cohen_kappa_score, confusion_matrix, f1_score, precision_score,
    recall_score, roc_auc_score,
)


def _safe_auc(function: Any, y: np.ndarray, probability: np.ndarray) -> float:
    return float(function(y, probability)) if len(np.unique(y)) == 2 else np.nan


def calculate_susceptibility_metrics(observed: Any, probability: Any, threshold: float = 0.5) -> dict[str, Any]:
    y = np.asarray(observed, dtype=int); p = np.clip(np.asarray(probability, dtype=float), 0, 1); prediction = (p >= float(threshold)).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
    return {
        "ROC_AUC": _safe_auc(roc_auc_score, y, p), "PR_AUC": _safe_auc(average_precision_score, y, p),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)), "precision": float(precision_score(y, prediction, zero_division=0)),
        "recall": float(recall_score(y, prediction, zero_division=0)), "sensitivity": float(recall_score(y, prediction, zero_division=0)),
        "specificity": float(tn / (tn + fp)) if tn + fp else np.nan, "F1": float(f1_score(y, prediction, zero_division=0)),
        "Cohen_Kappa": float(cohen_kappa_score(y, prediction)), "Brier": float(brier_score_loss(y, p)), "threshold": float(threshold),
        "true_negative": int(tn), "false_positive": int(fp), "false_negative": int(fn), "true_positive": int(tp), "sample_count": len(y),
    }


def calculate_reliability_bins(observed: Any, probability: Any, bins: int = 10) -> pd.DataFrame:
    y = np.asarray(observed, dtype=int); p = np.clip(np.asarray(probability, dtype=float), 0, 1); edges = np.linspace(0, 1, bins + 1); rows = []
    for index in range(bins):
        mask = (p >= edges[index]) & (p < edges[index + 1] if index < bins - 1 else p <= edges[index + 1])
        rows.append({"bin": index, "lower": edges[index], "upper": edges[index + 1], "sample_count": int(mask.sum()), "mean_probability": float(p[mask].mean()) if mask.any() else np.nan, "observed_frequency": float(y[mask].mean()) if mask.any() else np.nan})
    return pd.DataFrame(rows)


def calculate_calibration_error(observed: Any, probability: Any, bins: int = 10) -> float:
    reliability = calculate_reliability_bins(observed, probability, bins); total = reliability.sample_count.sum()
    return float(np.nansum(reliability.sample_count / total * np.abs(reliability.mean_probability - reliability.observed_frequency))) if total else np.nan


def evaluate_spatial_blocks(data: Any, probability_column: str = "probability", threshold: float = 0.5, block_column: str = "block_id") -> pd.DataFrame:
    frame = pd.DataFrame(data); rows = []
    for block, group in frame.groupby(block_column):
        metrics = calculate_susceptibility_metrics(group.label, group[probability_column], threshold)
        rows.append({"block_id": str(block), "split": str(group.split.iloc[0]) if "split" in group else "unknown", **metrics})
    return pd.DataFrame(rows)


def assess_spatial_stability(block_metrics: Any, metric: str = "PR_AUC") -> dict[str, Any]:
    frame = pd.DataFrame(block_metrics); values = pd.to_numeric(frame[metric], errors="coerce").dropna(); variance = float(values.var(ddof=0)) if len(values) else np.nan
    if not len(values): status = "unstable"
    elif variance <= 0.005: status = "stable"
    elif variance <= 0.02: status = "moderately_stable"
    else: status = "unstable"
    worst = str(frame.loc[pd.to_numeric(frame[metric], errors="coerce").idxmin(), "block_id"]) if len(values) else None; best = str(frame.loc[pd.to_numeric(frame[metric], errors="coerce").idxmax(), "block_id"]) if len(values) else None
    return {"status": status, "metric": metric, "metric_variance": variance, "worst_block": worst, "best_block": best, "spatially_unstable": status == "unstable"}


def select_validation_threshold(observed: Any, probability: Any) -> dict[str, Any]:
    candidates = np.linspace(0.1, 0.9, 81); rows = []
    for threshold in candidates:
        metrics = calculate_susceptibility_metrics(observed, probability, threshold); rows.append({"threshold": threshold, "score": 0.6 * metrics["balanced_accuracy"] + 0.4 * metrics["F1"], **metrics})
    selected = max(rows, key=lambda row: (row["score"], -abs(row["threshold"] - 0.5)))
    return {"threshold": float(selected["threshold"]), "selection_metric": "0.6 balanced_accuracy + 0.4 F1", "fit_split": "validation", "test_used": False, "validation_metrics": selected}


def calculate_model_value_added(metrics: Any) -> pd.DataFrame:
    frame = pd.DataFrame(metrics); validation = frame[frame.split == "validation"].copy(); baseline = validation[validation.model_id == "prevalence_baseline"].iloc[0]
    rows = []
    for row in validation.itertuples():
        improvement = float(row.PR_AUC - baseline.PR_AUC); brier_gain = float(baseline.Brier - row.Brier)
        rows.append({"model_id": row.model_id, "PR_AUC_improvement": improvement, "Brier_improvement": brier_gain, "value_added": "demonstrated" if improvement > 0.01 and brier_gain > 0 else "not_demonstrated", "comparison": "prevalence_baseline", "real_data_value_added": "not_tested"})
    result = pd.DataFrame(rows); logistic = result[result.model_id == "logistic_regression"]
    if len(logistic):
        logistic_pr = validation.loc[validation.model_id == "logistic_regression", "PR_AUC"].iloc[0]
        result["complex_vs_logistic"] = np.where(result.model_id.isin(["random_forest", "gradient_boosting"]), np.where(validation.set_index("model_id").reindex(result.model_id).PR_AUC.to_numpy() > logistic_pr + 0.01, "demonstrated", "not_demonstrated"), "not_applicable")
    return result


def validate_susceptibility_risk_language(text: str) -> dict[str, Any]:
    lowered = text.lower(); bad = "flood risk class" in lowered or "risk probability" in lowered
    return {"status": "passed" if not bad else "failed", "susceptibility_is_risk": False, "required_notice_present": "susceptibility" in lowered and "risk" in lowered}
