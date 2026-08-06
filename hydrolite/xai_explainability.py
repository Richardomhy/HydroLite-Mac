from __future__ import annotations

from importlib.util import find_spec
import numpy as np
import pandas as pd


def permutation_importance(model, features, target, seed=7):
    from sklearn.metrics import roc_auc_score
    rng=np.random.default_rng(seed); base=roc_auc_score(target, model.predict_proba(features)[:,1]); rows=[]
    for column in features.columns:
        shuffled=features.copy(); shuffled[column]=rng.permutation(shuffled[column].to_numpy()); rows.append({"feature":column,"importance":float(base-roc_auc_score(target,model.predict_proba(shuffled)[:,1])),"interpretation":"association, not causal effect"})
    return pd.DataFrame(rows).sort_values("importance",ascending=False)


def explain_model(model, features, target):
    ranking=permutation_importance(model,features,target); return {"status":"shap_available" if find_spec("shap") else "shap_optional_dependency_missing", "fallback":"permutation_importance", "global_importance":ranking, "local_explanations":features.head(10).assign(note="local association; not causal effect")}
