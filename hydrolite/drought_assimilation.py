from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def prepare_drought_assimilation_observations(data: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "subbasin_id", "variable", "value"}
    missing = sorted(required - set(data))
    if missing: raise ValueError(f"Assimilation observations missing: {missing}")
    result = data.copy(); result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    if result[["date", "value"]].isna().any().any(): raise ValueError("Assimilation observations contain invalid date/value")
    result["quality_status"] = result.get("quality_status", "ready")
    return result


def update_soil_moisture_state(state: dict[str, float], observation: float, gain: float) -> dict[str, Any]:
    if not 0 <= gain <= 1: raise ValueError("assimilation gain must be between 0 and 1")
    current = float(state["upper_soil_storage_mm"]) + float(state["lower_soil_storage_mm"])
    adjustment = gain * (float(observation) - current)
    upper_share = float(state["upper_soil_storage_mm"]) / max(current, 1e-9)
    updated = deepcopy(state)
    updated["upper_soil_storage_mm"] = max(float(state["upper_soil_storage_mm"]) + adjustment * upper_share, 0.0)
    updated["lower_soil_storage_mm"] = max(float(state["lower_soil_storage_mm"]) + adjustment * (1 - upper_share), 0.0)
    actual = updated["upper_soil_storage_mm"] + updated["lower_soil_storage_mm"] - current
    return {"state": updated, "assimilation_adjustment_mm": actual, "method": "soil_moisture_nudging"}


def update_groundwater_state(state: dict[str, float], observation: float, gain: float) -> dict[str, Any]:
    if not 0 <= gain <= 1: raise ValueError("assimilation gain must be between 0 and 1")
    current = float(state["groundwater_storage_mm"])
    updated = deepcopy(state); updated["groundwater_storage_mm"] = max(current + gain * (float(observation) - current), 0.0)
    return {"state": updated, "assimilation_adjustment_mm": updated["groundwater_storage_mm"] - current, "method": "groundwater_state_update"}


def update_reservoir_state(state: dict[str, float], observation: float) -> dict[str, Any]:
    current = float(state.get("reservoir_storage_m3", 0.0))
    updated = deepcopy(state); updated["reservoir_storage_m3"] = max(float(observation), 0.0)
    return {"state": updated, "assimilation_adjustment_m3": updated["reservoir_storage_m3"] - current, "method": "reservoir_storage_update"}


def run_drought_state_assimilation(state: dict[str, Any], observations: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    observations = prepare_drought_assimilation_observations(observations)
    analysis = deepcopy(state)
    adjustments = []
    for row in observations.itertuples(index=False):
        subbasin = str(row.subbasin_id)
        if subbasin not in analysis["subbasins"]: continue
        target = analysis["subbasins"][subbasin]
        if row.variable == "soil_moisture_mm":
            update = update_soil_moisture_state(target, row.value, float(config.get("soil_moisture_gain", 0.25)))
        elif row.variable == "groundwater_storage_mm":
            update = update_groundwater_state(target, row.value, float(config.get("groundwater_gain", 0.2)))
        elif row.variable == "reservoir_storage_m3":
            update = update_reservoir_state(target, row.value)
        else:
            continue
        analysis["subbasins"][subbasin] = update["state"]
        adjustments.append({"date": row.date, "subbasin_id": subbasin, "variable": row.variable, **{key:value for key,value in update.items() if key != "state"}})
    return {"status":"completed", "analysis_state":analysis, "forecast_state":deepcopy(analysis), "open_loop_state":deepcopy(state), "adjustments":pd.DataFrame(adjustments)}


def compare_open_loop_and_assimilated(result: dict[str, Any]) -> dict[str, Any]:
    def total(state, field):
        return sum(float(values.get(field, 0.0)) for values in state["subbasins"].values())
    fields = ["upper_soil_storage_mm","lower_soil_storage_mm","groundwater_storage_mm","reservoir_storage_m3"]
    return {field: {"open_loop":total(result["open_loop_state"],field),"analysis":total(result["analysis_state"],field),"difference":total(result["analysis_state"],field)-total(result["open_loop_state"],field)} for field in fields}


def validate_drought_assimilation(result: dict[str, Any]) -> dict[str, Any]:
    nonnegative = all(float(value) >= 0 for state in result["analysis_state"]["subbasins"].values() for key,value in state.items() if isinstance(value,(int,float)) and ("storage" in key or "soil" in key))
    adjustment_logged = "adjustments" in result
    return {"status":"passed" if nonnegative and adjustment_logged else "failed","nonnegative_states":nonnegative,"assimilation_adjustment_logged":adjustment_logged}


def write_drought_assimilation_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for label,key in (("open_loop","open_loop_state"),("analysis","analysis_state")):
        for subbasin,state in result[key]["subbasins"].items(): rows.append({"state_type":label,"subbasin_id":subbasin,**state})
    states=pd.DataFrame(rows);states[states.state_type=="open_loop"].to_csv(output/"open_loop_states.csv",index=False);states[states.state_type=="analysis"].to_csv(output/"analysis_states.csv",index=False)
    result["adjustments"].to_csv(output/"assimilation_adjustments.csv",index=False)
    comparison=compare_open_loop_and_assimilated(result)
    pd.DataFrame([{"variable":key,**value} for key,value in comparison.items()]).to_excel(output/"drought_assimilation_metrics.xlsx",index=False)
    for language,name in (("zh","drought_assimilation_report_zh.md"),("en","drought_assimilation_report_en.md")):
        title="# 干旱状态同化\n\n" if language=="zh" else "# Drought State Assimilation\n\n"
        (output/name).write_text(title+f"- method: `{result.get('method','nudging')}`\n- adjustments: `{len(result['adjustments'])}`\n\nAssimilation adjustments are explicit ledger entries and are never hidden as natural fluxes.\n",encoding="utf-8")
    if not states.empty:
        pivot=states.groupby("state_type")["groundwater_storage_mm"].mean()
        fig,ax=plt.subplots(figsize=(5,3.5));pivot.plot(kind="bar",ax=ax);ax.set_ylabel("groundwater storage (mm)")
        fig.tight_layout();fig.savefig(output/"open_loop_vs_assimilated_state.png",dpi=130);plt.close(fig)
    return {"adjustments":output/"assimilation_adjustments.csv","metrics":output/"drought_assimilation_metrics.xlsx","report_zh":output/"drought_assimilation_report_zh.md","report_en":output/"drought_assimilation_report_en.md"}
