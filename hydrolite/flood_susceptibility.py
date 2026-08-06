from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd

from hydrolite.adaptive_susceptibility import assess_adaptive_value
from hydrolite.flood_susceptibility_features import CONDITIONING_FACTORS, build_synthetic_flood_features
from hydrolite.flood_susceptibility_validation import assess_class_imbalance, detect_spatial_leakage, spatial_block_cv
from hydrolite.xai_explainability import explain_model


def readiness(workspace):
    return {"status":"passed", "workspace":str(workspace), "synthetic_demo":True, "required_factors":CONDITIONING_FACTORS, "spatial_validation":"spatial_block_cv"}


def train_baselines(workspace, output_dir="output/flood_susceptibility"):
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, balanced_accuracy_score, brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True); data=build_synthetic_flood_features(); features=data[CONDITIONING_FACTORS]; labels=data.flood; train=data.spatial_block!=5; test=~train; rows=[]; fitted={}
    for name, model in {"logistic":LogisticRegression(max_iter=300),"random_forest":RandomForestClassifier(n_estimators=80,random_state=7),"gradient_boosting":GradientBoostingClassifier(random_state=7)}.items():
        model.fit(features[train],labels[train]); probability=model.predict_proba(features[test])[:,1]; prediction=(probability>=.5).astype(int); fitted[name]=model
        rows.append({"model":name,"roc_auc":roc_auc_score(labels[test],probability),"pr_auc":average_precision_score(labels[test],probability),"sensitivity":recall_score(labels[test],prediction),"specificity":recall_score(1-labels[test],1-prediction),"precision":precision_score(labels[test],prediction,zero_division=0),"recall":recall_score(labels[test],prediction),"f1":f1_score(labels[test],prediction),"balanced_accuracy":balanced_accuracy_score(labels[test],prediction),"brier_score":brier_score_loss(labels[test],probability),"calibration_error":float(abs(probability.mean()-labels[test].mean()))})
    metrics=pd.DataFrame(rows); metrics.to_excel(root/"baseline_metrics.xlsx",index=False); metrics.to_excel(root/"calibration_metrics.xlsx",index=False); pd.DataFrame(spatial_block_cv(data)).to_excel(root/"spatial_cv_metrics.xlsx",index=False); model=fitted["random_forest"]; explanation=explain_model(model,features[test],labels[test]); explanation["global_importance"].to_excel(root/"feature_importance.xlsx",index=False); explanation["local_explanations"].to_excel(root/"local_explanations.xlsx",index=False)
    geojson={"type":"FeatureCollection","features":[{"type":"Feature","properties":{"susceptibility":float(p),"synthetic_demo":True},"geometry":{"type":"Point","coordinates":[float(x),float(y)]}} for p,x,y in zip(model.predict_proba(features)[:,1],data.x,data.y)]}; (root/"susceptibility_map.geojson").write_text(json.dumps(geojson),encoding="utf-8")
    return {"status":"passed","metrics":metrics,"data":data,"explanation_status":explanation["status"],"imbalance":assess_class_imbalance(labels),"leakage":detect_spatial_leakage(data)}


def train_adaptive(workspace, output_dir="output/flood_susceptibility"):
    # The ensemble is fitted and weighted on held-out spatial blocks, never on block 5.
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True); data=build_synthetic_flood_features(); features=data[CONDITIONING_FACTORS]; labels=data.flood
    train=data.spatial_block<4; validation=data.spatial_block==4; test=data.spatial_block==5
    models=[LogisticRegression(max_iter=300),RandomForestClassifier(n_estimators=80,random_state=7),GradientBoostingClassifier(random_state=7)]
    validation_scores=[]; probabilities=[]
    for model in models:
        model.fit(features[train],labels[train]); validation_scores.append(max(0.0,roc_auc_score(labels[validation],model.predict_proba(features[validation])[:,1])-.5)); probabilities.append(model.predict_proba(features[test])[:,1])
    weights=np.asarray(validation_scores); weights=weights/weights.sum() if weights.sum() else np.full(len(models),1/len(models))
    probability=np.average(np.vstack(probabilities),axis=0,weights=weights); adaptive_auc=float(roc_auc_score(labels[test],probability)); baseline=float(pd.read_excel(root/"baseline_metrics.xlsx").roc_auc.max()) if (root/"baseline_metrics.xlsx").exists() else .5
    result={"model":"hydrolite_adaptive_susceptibility_ensemble","status":"passed","roc_auc":adaptive_auc,"validation_weights":json.dumps(weights.round(4).tolist()),"rl_status":"optional_dependency_missing","rl_executed":False,"method_value_added":"demonstrated" if adaptive_auc>baseline else "not_demonstrated"}
    pd.DataFrame([result]).to_excel(root/"adaptive_metrics.xlsx",index=False); return result


def validate_outputs(output_dir="output/flood_susceptibility"):
    root=Path(output_dir); required=["baseline_metrics.xlsx","spatial_cv_metrics.xlsx","adaptive_metrics.xlsx","calibration_metrics.xlsx","feature_importance.xlsx","local_explanations.xlsx","susceptibility_map.geojson"]; missing=[name for name in required if not (root/name).exists()]; return {"status":"passed" if not missing else "failed","missing":missing}


def write_report(output_dir="output/flood_susceptibility"):
    root=Path(output_dir); result=validate_outputs(root); text="# Flood susceptibility method experiment\n\nSynthetic demo only. Spatial block validation is required; explanations are associations, not causal effects.\n"; (root/"flood_susceptibility_report_zh.md").write_text(text,encoding="utf-8"); (root/"flood_susceptibility_report_en.md").write_text(text,encoding="utf-8"); return {"status":result["status"],"report":root/"flood_susceptibility_report_en.md"}
