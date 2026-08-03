from __future__ import annotations

from pathlib import Path
from typing import Any
import pandas as pd


def audit_baseline_period(data:pd.DataFrame,baseline:tuple[str,str]|None=None)->dict[str,Any]:
    dates=pd.to_datetime(data.date);years=(dates.max()-dates.min()).days/365.25;return {"status":"limited_baseline_record" if years<30 else "adequate","years":years,"baseline":baseline}
def audit_spi_distribution(data:pd.DataFrame)->dict[str,Any]:return audit_baseline_period(data)
def audit_spei_distribution(data:pd.DataFrame)->dict[str,Any]:return audit_baseline_period(data)
def audit_ssi_distribution(data:pd.DataFrame)->dict[str,Any]:return audit_baseline_period(data)
def compare_parametric_empirical_indices(data:pd.DataFrame)->pd.DataFrame:return audit_monthwise_fitting(data)
def audit_monthwise_fitting(data:pd.DataFrame)->pd.DataFrame:return pd.DataFrame([{ "month":month,"records":len(group),"status":"limited_baseline_record" if len(group)<30 else "adequate"} for month,group in data.assign(month=pd.to_datetime(data.date).dt.month).groupby("month")])
def calculate_distribution_fit_diagnostics(data:pd.DataFrame)->pd.DataFrame:return audit_monthwise_fitting(data)
def classify_distribution_reliability(data:pd.DataFrame)->str:return "limited_baseline_record" if (data.status=="limited_baseline_record").any() else "adequate"
def write_distribution_audit_report(output_dir:str|Path,result:dict[str,Any])->Path:
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True);path=output/"distribution_audit_report.md";path.write_text("# Drought distribution audit\n\n"+str(result)+"\n",encoding="utf-8");return path
