from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib.util
import json

import numpy as np
import pandas as pd


def assess_drought_lstm_readiness(data: str | Path | pd.DataFrame | None = None, frequency: str = "daily") -> dict[str, Any]:
    if data is None: frame=pd.DataFrame()
    elif isinstance(data,(str,Path)): frame=pd.read_csv(data) if Path(data).is_file() else pd.DataFrame()
    else: frame=data
    records=len(frame)
    synthetic="synthetic_demo" in frame and bool(frame["synthetic_demo"].fillna(False).all())
    minimum=5000 if frequency=="daily" else 180
    torch_available=importlib.util.find_spec("torch") is not None
    return {"status":"synthetic_demo_only" if synthetic else "ready" if records>=minimum and torch_available else "optional_dependency_missing" if not torch_available else "insufficient_data","lstm_real_data_readiness":"insufficient_data" if synthetic or records<minimum else "ready","synthetic_demo":synthetic,"records":records,"minimum_records":minimum,"torch_available":torch_available}


def build_drought_lstm_sequences(data: pd.DataFrame, feature_columns: list[str], target_column: str, sequence_length: int=12):
    values=data[feature_columns].to_numpy(dtype=float);target=data[target_column].to_numpy(dtype=float);x=[];y=[]
    for index in range(sequence_length,len(data)): x.append(values[index-sequence_length:index]);y.append(target[index])
    return np.asarray(x),np.asarray(y)


def train_drought_lstm(*args, **kwargs):
    if importlib.util.find_spec("torch") is None: return {"status":"optional_dependency_missing","model":None}
    return {"status":"not_executed_mvp","model":None,"message":"Real LSTM training is outside this bounded MVP."}


def predict_drought_lstm(model, data):
    if model is None: return {"status":"model_missing","predictions":[]}
    return {"status":"not_executed_mvp","predictions":[]}


def evaluate_drought_lstm(observed, predicted):
    obs=np.asarray(observed,dtype=float);pred=np.asarray(predicted,dtype=float)
    return {"RMSE":float(np.sqrt(np.mean((obs-pred)**2)))} if len(obs) and len(obs)==len(pred) else {"RMSE":None}


def run_drought_lstm_synthetic_smoke_test(output_dir: str | Path) -> dict[str, Any]:
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    readiness=assess_drought_lstm_readiness()
    status="optional_dependency_missing" if not readiness["torch_available"] else "framework_smoke_only_no_training"
    result={**readiness,"status":status,"executed":False,"synthetic_demo":True}
    (output/"lstm_readiness.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (output/"drought_lstm_smoke_report.md").write_text("# Drought LSTM readiness\n\nNo PyTorch installation or real training is performed. The interface remains optional and gated by long continuous records and an independent test period.\n",encoding="utf-8")
    return result
