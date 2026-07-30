"""Explicit RUSLE-to-SDR sediment delivery MVP; missing processes stay missing."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import pandas as pd
import yaml


def _path(value: str | Path) -> Path: return Path(value).expanduser().resolve()


def load_rusle_subbasin_results(path: str | Path) -> pd.DataFrame:
    data = pd.read_excel(_path(path))
    if "baseline_total_t_yr" not in data: raise ValueError("RUSLE summary needs baseline_total_t_yr.")
    return data


def load_sdr_config(path: str | Path) -> dict[str, Any]:
    cfg = yaml.safe_load(_path(path).read_text(encoding="utf-8")) or {}; return validate_sdr_config(cfg)


def validate_sdr_config(config: dict[str, Any]) -> dict[str, Any]:
    mode = config.get("mode", "")
    if mode not in {"user_defined", "subbasin_lookup", "observed_calibrated", "area_empirical_demo", "connectivity_proxy_experimental"}: raise ValueError("Unsupported SDR mode.")
    value = config.get("sdr")
    if mode != "subbasin_lookup" and (value is None or not 0 <= float(value) <= 1): raise ValueError("SDR must be in [0, 1].")
    if mode == "area_empirical_demo" and not config.get("synthetic_demo", False): raise ValueError("area_empirical_demo is allowed only when synthetic_demo: true.")
    return config


def calculate_subbasin_sdr(subbasins: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    if config["mode"] == "subbasin_lookup": return subbasins["subbasin_id"].map(config.get("lookup", {})).astype(float)
    return pd.Series(float(config["sdr"]), index=subbasins.index)


def calculate_delivered_hillslope_sediment(soil_loss: Any, sdr: Any) -> Any: return pd.to_numeric(soil_loss) * pd.to_numeric(sdr)


def calculate_reservoir_trapping_efficiency(reservoir: dict[str, Any], config: dict[str, Any]) -> float | None:
    mode = config.get("mode", "unavailable")
    if mode == "unavailable": return None
    value = config.get("trapping_efficiency")
    if value is None or not 0 <= float(value) <= 1: raise ValueError("trapping_efficiency must be in [0, 1].")
    if mode == "capacity_inflow_proxy_experimental" and not config.get("synthetic_demo", False): raise ValueError("Experimental trapping proxy is not enabled for real projects.")
    return float(value)


def calculate_sediment_after_reservoir(delivered_sediment: float, trapping_efficiency: float | None) -> dict[str, float | None]:
    if trapping_efficiency is None: return {"trapped_sediment_t_yr": None, "released_sediment_t_yr": None}
    return {"trapped_sediment_t_yr": delivered_sediment*trapping_efficiency, "released_sediment_t_yr": delivered_sediment*(1-trapping_efficiency)}


def build_sediment_delivery_ledger(result: dict[str, Any]) -> pd.DataFrame:
    rows=[
        ("gross hillslope sheet/rill erosion",result.get("gross_hillslope_erosion_t_yr"),"available"),
        ("delivered hillslope sediment",result.get("delivered_hillslope_sediment_t_yr"),result.get("status","missing")),
        ("gully erosion",None,"missing"),("channel bed erosion",None,"missing"),("bank erosion",None,"missing"),("floodplain deposition",None,"missing"),
        ("reservoir trapping",result.get("trapped_sediment_t_yr"),"available" if result.get("trapped_sediment_t_yr") is not None else "missing"),
        ("outlet sediment yield",result.get("released_sediment_t_yr"),result.get("outlet_status","provisional_hillslope_delivery_only")),
        ("observed sediment load",None,"missing"),("residual",None,"partial")]
    return pd.DataFrame(rows,columns=["component","value_t_yr","status"])


def validate_sediment_delivery_result(result: dict[str, Any]) -> dict[str, Any]:
    errors=[]
    for name in ("sdr", "trapping_efficiency"):
        value=result.get(name)
        if value is not None and not 0 <= float(value) <= 1: errors.append(f"{name} outside [0,1]")
    return {"status":"passed" if not errors else "failed","errors":errors,"timescale":result.get("timescale","annual")}


def _run(rusle_dir: str | Path, sdr_config_path: str | Path, trapping_config_path: str | Path | None, output_dir: str | Path) -> dict[str, Any]:
    root=_path(output_dir);root.mkdir(parents=True,exist_ok=True);sub=load_rusle_subbasin_results(_path(rusle_dir)/"subbasin_soil_loss.xlsx");sdr_cfg=load_sdr_config(sdr_config_path);sdr=calculate_subbasin_sdr(sub,sdr_cfg);gross=pd.to_numeric(sub.baseline_total_t_yr);delivered=calculate_delivered_hillslope_sediment(gross,sdr)
    trap_cfg=yaml.safe_load(_path(trapping_config_path).read_text(encoding="utf-8")) if trapping_config_path else {"mode":"unavailable"};te=calculate_reservoir_trapping_efficiency({},trap_cfg or {"mode":"unavailable"});after=calculate_sediment_after_reservoir(float(delivered.sum()),te)
    result={"status":"provisional_hillslope_delivery_only" if te is None else "partial", "synthetic_demo":bool(sdr_cfg.get("synthetic_demo",False)), "uncalibrated":not bool(sdr_cfg.get("observed_calibrated",False)), "timescale":"annual", "sdr_mode":sdr_cfg["mode"], "sdr":float(sdr.iloc[0]), "gross_hillslope_erosion_t_yr":float(gross.sum()), "delivered_hillslope_sediment_t_yr":float(delivered.sum()), "trapping_efficiency":te, "trapping_efficiency_mode":(trap_cfg or {}).get("mode","unavailable"), **after}
    result["outlet_status"]="provisional_hillslope_delivery_only" if te is None else "provisional_missing_gully_channel_bank"
    table=sub[["subbasin_id"]].copy();table["gross_hillslope_erosion_t_yr"]=gross;table["sdr"]=sdr;table["delivered_hillslope_sediment_t_yr"]=delivered;table["method"]=result["sdr_mode"];table["calibration_status"]="uncalibrated_synthetic_demo" if result["synthetic_demo"] else "user_supplied"
    table.to_csv(root/"subbasin_sediment_delivery.csv",index=False)
    ledger=build_sediment_delivery_ledger(result)
    with pd.ExcelWriter(root/"sediment_delivery_summary.xlsx") as writer: pd.DataFrame([result]).to_excel(writer,sheet_name="summary",index=False);table.to_excel(writer,sheet_name="subbasins",index=False);ledger.to_excel(writer,sheet_name="ledger",index=False)
    ledger.to_excel(root/"sediment_delivery_ledger.xlsx",index=False)
    report=root/"sediment_delivery_report.md";report.write_text("# RUSLE-SDR sediment delivery MVP\n\nRUSLE is gross annual sheet/rill erosion. SDR estimates hillslope delivery only. Gully, bank, channel-bed and floodplain processes are missing, never zero. Synthetic demo is uncalibrated and not for engineering use.\n",encoding="utf-8")
    (root/"sediment_delivery_manifest.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return {**result,"output_dir":root,"ledger":ledger}


def write_sediment_delivery_outputs(output_dir: str | Path, result: dict[str, Any]) -> Path: return _path(output_dir)/"sediment_delivery_report.md"


def run_sediment_demo() -> dict[str, Any]:
    root=Path(__file__).resolve().parents[1];return _run(root/"output/rusle",root/"data_demo/sediment/demo_sdr_config.yaml",root/"data_demo/sediment/demo_reservoir_trapping.yaml",root/"output/sediment_delivery")


def validate_sediment_outputs(output_dir: str | Path) -> dict[str, Any]:
    root=_path(output_dir);required=["subbasin_sediment_delivery.csv","sediment_delivery_summary.xlsx","sediment_delivery_ledger.xlsx","sediment_delivery_report.md","sediment_delivery_manifest.json"];missing=[x for x in required if not (root/x).exists()];return {"status":"passed" if not missing else "failed","missing":missing}
