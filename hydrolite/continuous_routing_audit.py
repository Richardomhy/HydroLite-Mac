from __future__ import annotations

from pathlib import Path
from typing import Any
import pandas as pd


def collect_routing_outputs(output_dir: str | Path) -> pd.DataFrame: return pd.read_csv(Path(output_dir) / "daily_routing.csv", parse_dates=["date"])
def audit_subbasin_generated_runoff(result:dict[str,Any])->pd.DataFrame:return result["fluxes"].groupby("subbasin_id",as_index=False).runoff_to_channel_m3.sum()
def audit_surface_interflow_baseflow_partition(result:dict[str,Any])->pd.DataFrame:return result["fluxes"][["surface_runoff_mm","interflow_mm","baseflow_mm"]].sum().to_frame("mm").reset_index(names="component")
def audit_network_inflow_outflow(result:dict[str,Any])->dict[str,Any]:return calculate_routing_mass_balance(result["routing"])
def audit_reach_storage_continuity(result:dict[str,Any])->dict[str,Any]:return calculate_routing_mass_balance(result["routing"])
def audit_outlet_flow_conversion(result:dict[str,Any])->pd.DataFrame:return result["routing"].assign(outflow_cms=lambda x:x.outflow_m3/86400)
def compare_generated_depth_to_outlet_volume(result:dict[str,Any])->dict[str,Any]:return {"generated_m3":float(result["fluxes"].runoff_to_channel_m3.sum()),"outlet_m3":float(result["routing"].outflow_m3.sum())}
def write_continuous_routing_audit(output_dir:str|Path,result:dict[str,Any])->Path:return write_routing_audit_report(output_dir,result)
def calculate_routing_mass_balance(data: pd.DataFrame) -> dict[str, Any]: return {"status": "passed" if float(data.residual_m3.abs().max()) <= 1e-6 else "failed", "inflow_m3": float(data.inflow_m3.sum()), "outflow_m3": float(data.outflow_m3.sum()), "final_storage_m3": float(data.final_storage_m3.iloc[-1]), "residual_m3": float(data.residual_m3.sum())}
def audit_subbasin_outlet_contribution(fluxes: pd.DataFrame) -> pd.DataFrame: return fluxes.groupby("subbasin_id", as_index=False).runoff_to_channel_m3.sum().rename(columns={"runoff_to_channel_m3": "contribution_m3"})
def compare_pre_post_routing_flow(routing: pd.DataFrame) -> pd.DataFrame: return routing[["date", "inflow_m3", "outflow_m3", "initial_storage_m3", "final_storage_m3"]].copy()
def validate_routing_parameters(config: dict[str, Any]) -> dict[str, Any]:
    r = config.get("routing", {}); k = float(r.get("k_days", 0)); x = float(r.get("x", 0)); return {"status": "passed" if k > 0 and 0 <= x <= .5 else "failed", "k_days": k, "x": x}
def write_routing_audit_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    output=Path(output_dir); output.mkdir(parents=True,exist_ok=True); path=output/"routing_audit_report.md"; path.write_text("# Continuous routing audit\n\n"+str(result)+"\n",encoding="utf-8"); return path
