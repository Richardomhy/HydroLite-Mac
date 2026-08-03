from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hydrolite.continuous_calibration import evaluate_continuous_model


def build_climatology_benchmark(observed: pd.DataFrame) -> pd.Series:
    dates=pd.to_datetime(observed.date); return dates.dt.month.map(observed.assign(month=dates.dt.month).groupby("month").streamflow_cms.mean()).rename("climatology_cms")
def build_persistence_benchmark(observed: pd.DataFrame) -> pd.Series: return observed.streamflow_cms.shift(1).bfill().rename("persistence_cms")
def build_monthly_runoff_coefficient_benchmark(forcing: pd.DataFrame, observed: pd.DataFrame, area_km2: float) -> pd.Series:
    rain=forcing.groupby("date",as_index=False).precipitation_mm.mean(); rain.date=pd.to_datetime(rain.date); obs=observed.copy();obs.date=pd.to_datetime(obs.date); frame=obs.merge(rain,on="date",how="left");month=frame.date.dt.month; coeff=(frame.streamflow_cms*86400/(frame.precipitation_mm*area_km2*1000).replace(0,np.nan)).groupby(month).median().fillna(0); return (frame.precipitation_mm*area_km2*1000*month.map(coeff)/86400).rename("runoff_coefficient_cms")
def build_rainfall_linear_reservoir_benchmark(forcing: pd.DataFrame, area_km2: float, coefficient: float=.08, k_days: float=3) -> pd.Series:
    rain=forcing.groupby("date").precipitation_mm.mean().to_numpy(); state=0.;out=[]
    for value in rain: state=(state+value*area_km2*1000*coefficient)/(1+1/k_days);out.append(state/k_days/86400)
    return pd.Series(out,name="linear_reservoir_cms")
def build_observed_monthly_climatology_diagnostic(observed: pd.DataFrame) -> pd.DataFrame: return observed.assign(month=pd.to_datetime(observed.date).dt.month).groupby("month",as_index=False).streamflow_cms.agg(["mean","min","max"]).reset_index()
def climatological_mean_flow(observed:pd.DataFrame)->pd.Series:return build_climatology_benchmark(observed)
def previous_day_persistence(observed:pd.DataFrame)->pd.Series:return build_persistence_benchmark(observed)
def monthly_runoff_coefficient(forcing:pd.DataFrame,observed:pd.DataFrame,area_km2:float)->pd.Series:return build_monthly_runoff_coefficient_benchmark(forcing,observed,area_km2)
def rainfall_linear_reservoir(forcing:pd.DataFrame,area_km2:float)->pd.Series:return build_rainfall_linear_reservoir_benchmark(forcing,area_km2)
def evaluate_benchmark_models(results:dict[str,Any],observed:pd.DataFrame)->pd.DataFrame:return results["metrics"]
def compare_hydrolite_to_benchmarks(hydrolite:dict[str,float],benchmarks:pd.DataFrame)->dict[str,Any]:return {"hydrolite_nse":hydrolite.get("NSE"),"best_benchmark_nse":float(benchmarks.NSE.max())}
def classify_model_value_added(result:dict[str,Any])->str:return "demonstrated" if result.get("hydrolite_nse",-np.inf)>result.get("best_benchmark_nse",np.inf) else "not_demonstrated"


def run_continuous_benchmarks(forcing: pd.DataFrame, observed: pd.DataFrame, simulated: pd.Series, area_km2: float) -> dict[str, Any]:
    observed=observed.sort_values("date").reset_index(drop=True); output=pd.DataFrame({"date":pd.to_datetime(observed.date),"observed_cms":observed.streamflow_cms,"hydrolite_cms":np.asarray(simulated)})
    output["climatology_cms"]=build_climatology_benchmark(observed);output["persistence_cms"]=build_persistence_benchmark(observed);output["runoff_coefficient_cms"]=build_monthly_runoff_coefficient_benchmark(forcing,observed,area_km2);output["linear_reservoir_cms"]=build_rainfall_linear_reservoir_benchmark(forcing,area_km2)
    metrics=[]
    for name in output.columns[2:]: metrics.append({"model":name.replace("_cms",""),**evaluate_continuous_model(output[name],output.observed_cms)})
    return {"timeseries":output,"metrics":pd.DataFrame(metrics)}


def write_benchmark_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True);result["timeseries"].to_csv(output/"benchmark_timeseries.csv",index=False);result["metrics"].to_excel(output/"benchmark_metrics.xlsx",index=False)
    fig,ax=plt.subplots(figsize=(8,3));result["metrics"].plot.bar(x="model",y="NSE",ax=ax,legend=False);fig.tight_layout();fig.savefig(output/"benchmark_comparison.png",dpi=120);plt.close(fig)
    (output/"benchmark_report.md").write_text("# Continuous benchmarks\n\nBenchmarks are diagnostic baselines, not calibrated forecasts.\n",encoding="utf-8")
    return {"metrics":output/"benchmark_metrics.xlsx","report":output/"benchmark_report.md"}
