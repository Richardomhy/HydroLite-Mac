"""Supervised probability baselines with train-only preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from hydrolite.flood_susceptibility_evaluation import calculate_calibration_error, calculate_susceptibility_metrics, select_validation_threshold


MODEL_COMPLEXITY = {"prevalence_baseline": "constant", "logistic_regression": "simple", "random_forest": "complex", "gradient_boosting": "complex"}


@dataclass(slots=True)
class SusceptibilityModel:
    model_id: str
    estimator: Any
    numeric_factors: list[str]
    categorical_factors: list[str]
    preprocessing_manifest: dict[str, Any]

    def predict_proba(self, data: Any) -> np.ndarray:
        return self.estimator.predict_proba(pd.DataFrame(data))[:, 1]


@dataclass(slots=True)
class ProbabilityCalibrator:
    method: str
    estimator: Any = None

    def predict(self, probability: Any) -> np.ndarray:
        p = np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)
        if self.method == "uncalibrated": return p
        if self.method == "sigmoid": return self.estimator.predict_proba(np.log(p / (1 - p)).reshape(-1, 1))[:, 1]
        return np.clip(self.estimator.predict(p), 0, 1)


class PrevalenceEstimator:
    def __init__(self, prevalence: float): self.prevalence = float(prevalence)
    def predict_proba(self, data: Any) -> np.ndarray:
        p = np.full(len(pd.DataFrame(data)), self.prevalence); return np.column_stack([1 - p, p])


def build_preprocessor(numeric_factors: Sequence[str], categorical_factors: Sequence[str]) -> ColumnTransformer:
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median")), ("standardizer", StandardScaler())])
    categorical = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False))])
    return ColumnTransformer([("numeric", numeric, list(numeric_factors)), ("categorical", categorical, list(categorical_factors))], sparse_threshold=0)


def fit_supervised_models(train: Any, factors: Sequence[str], categorical_factors: Sequence[str], seed: int = 7) -> dict[str, SusceptibilityModel]:
    frame = pd.DataFrame(train); numeric = [name for name in factors if name not in categorical_factors]; categorical = [name for name in categorical_factors if name in factors]
    x = frame[list(factors)]; y = frame.label.astype(int); prevalence = float(y.mean()); manifest = {"fit_split": "train", "validation_or_test_fit": False, "imputation_fit": "train", "standardization_fit": "train", "encoding_fit": "train"}
    models: dict[str, Any] = {
        "prevalence_baseline": PrevalenceEstimator(prevalence),
        "logistic_regression": Pipeline([("preprocessor", build_preprocessor(numeric, categorical)), ("model", LogisticRegression(max_iter=500, class_weight="balanced", random_state=seed))]),
        "random_forest": Pipeline([("preprocessor", build_preprocessor(numeric, categorical)), ("model", RandomForestClassifier(n_estimators=160, max_depth=8, min_samples_leaf=5, class_weight="balanced", random_state=seed, n_jobs=1))]),
        "gradient_boosting": Pipeline([("preprocessor", build_preprocessor(numeric, categorical)), ("model", GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=.04, random_state=seed))]),
    }
    result = {}
    sample_weight = np.where(y == 1, len(y) / (2 * max(int(y.sum()), 1)), len(y) / (2 * max(int((y == 0).sum()), 1)))
    for model_id, estimator in models.items():
        if model_id != "prevalence_baseline":
            if model_id == "gradient_boosting": estimator.fit(x, y, model__sample_weight=sample_weight)
            else: estimator.fit(x, y)
        result[model_id] = SusceptibilityModel(model_id, estimator, numeric, categorical, dict(manifest))
    return result


def fit_probability_calibrators(validation_labels: Any, probability: Any) -> dict[str, ProbabilityCalibrator]:
    y = np.asarray(validation_labels, dtype=int); p = np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)
    sigmoid = LogisticRegression().fit(np.log(p / (1 - p)).reshape(-1, 1), y)
    isotonic = IsotonicRegression(out_of_bounds="clip").fit(p, y)
    return {"uncalibrated": ProbabilityCalibrator("uncalibrated"), "sigmoid": ProbabilityCalibrator("sigmoid", sigmoid), "isotonic": ProbabilityCalibrator("isotonic", isotonic)}


def select_calibration_on_validation(validation_labels: Any, probability: Any) -> tuple[ProbabilityCalibrator, pd.DataFrame]:
    rows = []; calibrators = fit_probability_calibrators(validation_labels, probability)
    for method, calibrator in calibrators.items():
        calibrated = calibrator.predict(probability); metrics = calculate_susceptibility_metrics(validation_labels, calibrated); rows.append({"calibration_method": method, "Brier": metrics["Brier"], "calibration_error": calculate_calibration_error(validation_labels, calibrated), "fit_split": "validation", "test_used": False})
    metrics = pd.DataFrame(rows).sort_values(["Brier", "calibration_error", "calibration_method"]); selected = str(metrics.iloc[0].calibration_method)
    metrics["selected"] = metrics.calibration_method == selected
    return calibrators[selected], metrics


def evaluate_candidates(models: dict[str, SusceptibilityModel], validation: Any, test: Any, factors: Sequence[str]) -> tuple[pd.DataFrame, dict[str, Any], dict[str, ProbabilityCalibrator], pd.DataFrame]:
    validation_frame = pd.DataFrame(validation); test_frame = pd.DataFrame(test); metrics = []; calibrators = {}; calibration_rows = []; artifacts = {}
    for model_id, model in models.items():
        validation_raw = model.predict_proba(validation_frame[list(factors)]); test_raw = model.predict_proba(test_frame[list(factors)])
        calibrator, calibration = select_calibration_on_validation(validation_frame.label, validation_raw); calibrators[model_id] = calibrator; calibration.insert(0, "model_id", model_id); calibration_rows.append(calibration)
        validation_probability = calibrator.predict(validation_raw); threshold = select_validation_threshold(validation_frame.label, validation_probability); test_probability = calibrator.predict(test_raw)
        for split, frame, probability in (("validation", validation_frame, validation_probability), ("test", test_frame, test_probability)):
            metrics.append({"model_id": model_id, "split": split, "complexity": MODEL_COMPLEXITY[model_id], "calibration_method": calibrator.method, **calculate_susceptibility_metrics(frame.label, probability, threshold["threshold"])})
        artifacts[model_id] = {"validation_probability": validation_probability, "test_probability": test_probability, "threshold": threshold}
    return pd.DataFrame(metrics), artifacts, calibrators, pd.concat(calibration_rows, ignore_index=True)


def select_susceptibility_model(validation_metrics: Any, validation_block_metrics: Any) -> dict[str, Any]:
    metrics = pd.DataFrame(validation_metrics); metrics = metrics[metrics.split == "validation"].copy(); blocks = pd.DataFrame(validation_block_metrics)
    variance = blocks.groupby("model_id").PR_AUC.var(ddof=0).fillna(0).to_dict() if len(blocks) else {}
    metrics["spatial_variance"] = metrics.model_id.map(variance).fillna(0)
    metrics["selection_score"] = 0.4 * metrics.PR_AUC + 0.25 * (1 - metrics.Brier) + 0.25 * metrics.balanced_accuracy + 0.1 * (1 - np.minimum(metrics.spatial_variance / .05, 1))
    ranked = metrics.sort_values(["selection_score", "complexity", "model_id"], ascending=[False, True, True]); best = ranked.iloc[0]
    logistic = ranked[ranked.model_id == "logistic_regression"]
    if len(logistic) and float(best.selection_score - logistic.iloc[0].selection_score) <= 0.01: best = logistic.iloc[0]; reason = "Logistic preferred because validation composite score is within 0.01 of the best complex model."
    else: reason = "Highest validation composite of PR-AUC, Brier, balanced accuracy, and spatial stability."
    return {"selected_model": str(best.model_id), "selection_reason": reason, "validation_score": float(best.selection_score), "complexity": str(best.complexity), "test_used_for_selection": False, "selection_metrics": ["PR_AUC", "Brier", "balanced_accuracy", "spatial_variance"]}


def assess_rl_suitability(context: Any | None = None) -> dict[str, Any]:
    payload = dict(context or {}); sequential = bool(payload.get("sequential_decision", False)); action_changes = bool(payload.get("action_changes_environment", False)); reward = bool(payload.get("decision_linked_reward", False)); transitions = bool(payload.get("real_state_transition", False))
    if not any((sequential, action_changes, reward, transitions)): status = "rl_not_justified"
    elif all((sequential, action_changes, reward, transitions)): status = "rl_potentially_useful"
    elif sequential and transitions: status = "rl_research_only"
    else: status = "insufficient_evidence"
    return {"status": status, "static_classification": not sequential, "checks": {"sequential_decision": sequential, "action_changes_environment": action_changes, "decision_linked_reward": reward, "real_state_transition": transitions}, "rl_implemented": False, "rl_dependencies_required": False}
