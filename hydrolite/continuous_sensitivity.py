from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hydrolite.continuous_calibration import build_continuous_parameter_bounds, evaluate_continuous_model
from hydrolite.continuous_hydrology import initialize_continuous_state, run_continuous_period


def generate_oat_sensitivity_samples(parameters: dict[str, float], fraction: float = .1) -> pd.DataFrame:
    rows=[]
    for name in build_continuous_parameter_bounds(parameters):
        for multiplier in (1-fraction, 1+fraction): rows.append({"parameter":name,"multiplier":multiplier,"value":parameters[name]*multiplier})
    return pd.DataFrame(rows)

def build_parameter_sample(parameters:dict[str,float],bounds:dict[str,tuple[float,float]],method:str="lhs",count:int=16,seed:int=42)->pd.DataFrame:return generate_lhs_parameter_samples(bounds,count,seed) if method.lower() in {"lhs","latin_hypercube"} else generate_oat_sensitivity_samples(parameters)
def calculate_oat_sensitivity(results:pd.DataFrame)->pd.DataFrame:return results.copy()
def calculate_rank_correlation_sensitivity(results:pd.DataFrame)->pd.DataFrame:return results.corr(numeric_only=True,method="spearman")
def calculate_elementary_effects(results:pd.DataFrame)->pd.DataFrame:return results.diff().abs().mean(numeric_only=True).rename("elementary_effect").reset_index(names="parameter")
def calculate_parameter_response_curves(results:pd.DataFrame)->pd.DataFrame:return results.copy()
def calculate_parameter_identifiability(results:pd.DataFrame)->pd.DataFrame:return results.copy()
def detect_parameter_interactions(results:pd.DataFrame)->pd.DataFrame:return results.corr(numeric_only=True)
def classify_parameter_sensitivity(result:float)->str:return "sensitive" if abs(result)>=.3 else "moderately_sensitive" if abs(result)>=.1 else "weakly_sensitive" if abs(result)>0 else "unidentifiable"


def generate_lhs_parameter_samples(bounds: dict[str, tuple[float, float]], n: int = 16, seed: int = 42) -> pd.DataFrame:
    rng=np.random.default_rng(seed); matrix=np.zeros((n,len(bounds)))
    for i,(name,(lo,hi)) in enumerate(bounds.items()): matrix[:,i]=(rng.permutation(n)+rng.random(n))/n*(hi-lo)+lo
    return pd.DataFrame(matrix,columns=list(bounds))


def run_continuous_sensitivity(forcing: pd.DataFrame, config: dict[str, Any], parameters: dict[str, float], observed: pd.DataFrame | None = None, n: int = 16) -> dict[str, Any]:
    bounds=build_continuous_parameter_bounds(parameters); samples=generate_lhs_parameter_samples(bounds,n)
    rows=[]
    for i,row in samples.iterrows():
        candidate={**parameters,**row.to_dict()}; result=run_continuous_period(forcing,candidate,initialize_continuous_state(config),config); out=result["routing"].outflow_m3.to_numpy()/86400
        metrics={"total_outflow_m3":float(result["routing"].outflow_m3.sum()),"peak_flow_cms":float(out.max())}
        if observed is not None:
            metrics.update(evaluate_continuous_model(out,observed.streamflow_cms.to_numpy()))
        rows.append({"sample_id":i+1,**row.to_dict(),**metrics})
    metrics=pd.DataFrame(rows); corr=[]
    for name in bounds:
        corr.append({"parameter":name,"rank_correlation_total_outflow":float(metrics[name].corr(metrics.total_outflow_m3,method="spearman")),"rank_correlation_peak":float(metrics[name].corr(metrics.peak_flow_cms,method="spearman"))})
    ranking=pd.DataFrame(corr); ranking["importance"] = ranking[["rank_correlation_total_outflow","rank_correlation_peak"]].abs().max(axis=1); ranking["identifiability"] = np.where(ranking.importance<.05,"weak","informative")
    return {"samples":samples,"metrics":metrics,"identifiability":ranking,"interactions":metrics.corr(numeric_only=True)}


def write_continuous_sensitivity_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    with pd.ExcelWriter(output/"sensitivity_samples.xlsx") as writer: result["samples"].to_excel(writer,index=False)
    with pd.ExcelWriter(output/"sensitivity_metrics.xlsx") as writer: result["metrics"].to_excel(writer,index=False)
    result["identifiability"].to_excel(output/"parameter_identifiability.xlsx",index=False);result["interactions"].to_excel(output/"parameter_interactions.xlsx")
    fig,ax=plt.subplots(figsize=(7,3));result["identifiability"].sort_values("importance").plot.barh(x="parameter",y="importance",legend=False,ax=ax);fig.tight_layout();fig.savefig(output/"sensitivity_ranking.png",dpi=120);plt.close(fig)
    for name,title in (("sensitivity_report_zh.md","# 连续模型灵敏度\n"),("sensitivity_report_en.md","# Continuous sensitivity\n")):(output/name).write_text(title+"Fixed-seed LHS only; no SALib dependency.\n",encoding="utf-8")
    return {"metrics":output/"sensitivity_metrics.xlsx","report":output/"sensitivity_report_zh.md"}
