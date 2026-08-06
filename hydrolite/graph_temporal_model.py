from __future__ import annotations

from importlib.util import find_spec

ALLOWED_MODES = {"graph_feature_only", "graph_linear_residual", "graph_mlp_residual", "graph_unidirectional_lstm", "graph_causal_tcn", "graph_causal_attention", "graph_bidirectional_hindcast_only"}


def validate_graph_temporal_mode(mode: str, purpose: str = "forecast") -> dict:
    if mode not in ALLOWED_MODES: return {"status": "failed", "reason": "unknown_mode"}
    if purpose == "forecast" and mode == "graph_bidirectional_hindcast_only": return {"status": "future_context_leakage_blocked", "mode": mode, "recommendation": "graph_unidirectional_lstm, graph_causal_tcn, or graph_causal_attention"}
    if mode in {"graph_mlp_residual", "graph_unidirectional_lstm", "graph_causal_tcn", "graph_causal_attention"} and find_spec("torch") is None: return {"status": "optional_dependency_missing", "mode": mode, "dependency": "torch"}
    return {"status": "passed", "mode": mode, "purpose": purpose}


def fit_graph_linear_residual(physical_prediction, observed, features=None):
    import numpy as np
    physical, target = np.asarray(physical_prediction, dtype=float), np.asarray(observed, dtype=float)
    residual = target - physical; design = np.c_[np.ones(len(physical)), physical] if features is None else np.c_[np.ones(len(physical)), np.asarray(features, dtype=float)]
    coefficients = np.linalg.lstsq(design, residual, rcond=None)[0]; correction = design @ coefficients; corrected = np.maximum(0, physical + correction)
    return {"physical_prediction": physical, "residual_correction": correction, "corrected_prediction": corrected, "correction_fraction": correction / np.maximum(np.abs(physical), 1e-9), "correction_uncertainty": float(np.std(residual - correction)), "coefficients": coefficients.tolist()}
