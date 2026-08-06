from __future__ import annotations

def assess_adaptive_value(baseline_auc, adaptive_auc=None, rl_available=False):
    if not rl_available: return {"status":"optional_dependency_missing", "rl_executed":False, "method_value_added":"not_demonstrated"}
    return {"status":"demonstrated" if adaptive_auc and adaptive_auc>baseline_auc else "no_demonstrated_value_added", "rl_executed":True, "method_value_added":"demonstrated" if adaptive_auc and adaptive_auc>baseline_auc else "not_demonstrated"}
