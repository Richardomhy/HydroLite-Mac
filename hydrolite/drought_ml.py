from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib.util
import json

import numpy as np
import pandas as pd


MODELS = ("persistence", "climatology", "linear_regression", "ridge", "random_forest", "gradient_boosting")


def assess_drought_ml_readiness(data: str | Path | pd.DataFrame, frequency: str = "daily") -> dict[str, Any]:
    frame = pd.read_csv(data) if isinstance(data, (str, Path)) and Path(data).is_file() else (pd.DataFrame() if isinstance(data, (str, Path)) else data.copy())
    minimum = 3650 if frequency == "daily" else 120
    test_minimum = 730 if frequency == "daily" else 24
    valid = int(frame.dropna().shape[0])
    sklearn = importlib.util.find_spec("sklearn") is not None
    synthetic = "synthetic_demo" in frame and bool(frame["synthetic_demo"].fillna(False).all())
    return {
        "status": "synthetic_demo_only" if synthetic else "ready" if valid >= minimum and sklearn else "insufficient_data" if valid < minimum else "optional_dependency_missing",
        "ml_real_data_readiness": "insufficient_data" if synthetic or valid < minimum else "ready",
        "synthetic_demo": synthetic,
        "records": valid, "minimum_records": minimum, "minimum_test_records": test_minimum,
        "sklearn_available": sklearn, "chronological_split_required": True, "test_scaler_fit_prohibited": True,
    }


def split_drought_ml_data_chronologically(data: pd.DataFrame, train_fraction: float = 0.7, validation_fraction: float = 0.15) -> dict[str, pd.DataFrame]:
    frame=data.sort_values("date").reset_index(drop=True);first=int(len(frame)*train_fraction);second=first+int(len(frame)*validation_fraction)
    return {"train":frame.iloc[:first].copy(),"validation":frame.iloc[first:second].copy(),"test":frame.iloc[second:].copy()}


def run_drought_ml_synthetic_demo(output_dir: str | Path) -> dict[str, Any]:
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(7);months=240
    x=np.sin(np.arange(months)*2*np.pi/12)+rng.normal(0,0.2,months);y=np.roll(x,1)*0.7+rng.normal(0,0.25,months);y[0]=0
    frame=pd.DataFrame({"date":pd.date_range("2000-01-01",periods=months,freq="MS"),"antecedent_index":x,"target_index":y})
    split=split_drought_ml_data_chronologically(frame)
    prediction=split["test"]["antecedent_index"].to_numpy()*0.7
    rmse=float(np.sqrt(np.mean((prediction-split["test"]["target_index"].to_numpy())**2)))
    metrics=pd.DataFrame([{"model":"synthetic_linear_baseline","RMSE":rmse,"synthetic_demo":True,"test_records":len(split["test"])}])
    metrics.to_excel(output/"drought_ml_metrics.xlsx",index=False)
    readiness={"status":"synthetic_demo_only","ml_real_data_readiness":"insufficient_data","synthetic_demo":True,"models":MODELS}
    (output/"ml_readiness.json").write_text(json.dumps(readiness,indent=2),encoding="utf-8")
    (output/"drought_ml_report.md").write_text("# Drought ML synthetic demo\n\nSynthetic data verify the workflow only. They are not real training evidence, and chronological splits prevent future leakage.\n",encoding="utf-8")
    return {**readiness,"metrics":metrics}
