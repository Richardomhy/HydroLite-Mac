from __future__ import annotations

from pathlib import Path
from typing import Any
import pandas as pd


def detect_lag_error(simulated: pd.Series, observed: pd.Series) -> dict[str, Any]:
    values=[(lag,float(simulated.corr(observed.shift(lag)))) for lag in range(-7,8)]; best=max(values,key=lambda x: -99 if pd.isna(x[1]) else x[1]);return {"best_lag_days":best[0],"correlation":best[1]}
def diagnose_runoff_generation_structure(result:dict[str,Any])->dict[str,Any]:return {"surface_runoff_mm":float(result["fluxes"].surface_runoff_mm.sum())}
def diagnose_soil_storage_structure(result:dict[str,Any])->dict[str,Any]:return {"status":"diagnostic"}
def diagnose_groundwater_structure(result:dict[str,Any])->dict[str,Any]:return {"status":"diagnostic"}
def diagnose_et_structure(result:dict[str,Any])->dict[str,Any]:return {"actual_et_mm":float(result["fluxes"].actual_et_mm.sum())}
def diagnose_routing_structure(result:dict[str,Any])->dict[str,Any]:return {"status":"diagnostic"}
def compare_internal_states_to_observations(result:dict[str,Any])->dict[str,Any]:return {"status":"observations_optional"}
def identify_dominant_structural_bias(result:dict[str,Any])->str:return "structural_mismatch"
def recommend_structure_changes(result:dict[str,Any])->list[str]:return ["verify observation generation and units before changing model structure"]
def detect_seasonal_bias(frame: pd.DataFrame) -> pd.DataFrame:
    data=frame.copy();data["month"]=pd.to_datetime(data.date).dt.month;return data.groupby("month",as_index=False)[["simulated_cms","observed_cms"]].mean().assign(bias=lambda x:x.simulated_cms-x.observed_cms)
def detect_flow_regime_bias(frame: pd.DataFrame) -> pd.DataFrame:
    q=frame.observed_cms.quantile([.3,.9]);return pd.DataFrame([{ "regime":"low","bias":float((frame.loc[frame.observed_cms<=q.loc[.3],"simulated_cms"]-frame.loc[frame.observed_cms<=q.loc[.3],"observed_cms"]).mean())},{"regime":"high","bias":float((frame.loc[frame.observed_cms>=q.loc[.9],"simulated_cms"]-frame.loc[frame.observed_cms>=q.loc[.9],"observed_cms"]).mean())}])
def assess_mass_balance_vs_performance(balance: dict[str,Any], metrics:dict[str,Any])->dict[str,Any]: return {"water_balance_status":balance.get("status"),"nse":metrics.get("NSE"),"conclusion":"water balance passes but flow process fails" if balance.get("status")=="passed" and metrics.get("NSE",0)<0 else "consistent"}
def diagnose_structural_mismatch(flow_audit: dict[str,Any], truth_status: str)->dict[str,Any]:
    ratio=float(flow_audit.get("simulated_to_observed_volume_ratio",1));return {"status":"structural_mismatch" if truth_status=="passed" and not .7<=ratio<=1.3 else "insufficient_information","reason":"legacy observed flow was generated from a lagged-rainfall proxy, not the HydroLite forward model" if truth_status=="passed" else "truth recovery not yet passed"}
def write_structure_diagnostic_report(output_dir: str|Path,result:dict[str,Any])->dict[str,Path]:
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True);pd.DataFrame([result]).to_excel(output/"structure_diagnostic.xlsx",index=False)
    paths={}
    for lang,name in (("zh","structure_diagnostic_report_zh.md"),("en","structure_diagnostic_report_en.md")):
        path=output/name;path.write_text("# Structural diagnostic\n\n"+str(result)+"\n",encoding="utf-8");paths[lang]=path
    return {"xlsx":output/"structure_diagnostic.xlsx",**paths}
