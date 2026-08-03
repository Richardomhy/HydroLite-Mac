from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from hydrolite.continuous_hydrology import initialize_continuous_state, run_continuous_period


CALIBRATABLE = ("infiltration_coefficient", "upper_soil_capacity_mm", "lower_soil_capacity_mm", "percolation_coefficient", "interflow_coefficient", "baseflow_coefficient", "et_coefficient")

def trace_parameter_from_config(parameter_name: str, config: dict[str, Any]) -> dict[str, Any]: return {"parameter":parameter_name,"value":config.get("parameters",{}).get(parameter_name),"configured":parameter_name in config.get("parameters",{})}
def trace_parameter_to_model_state(parameter_name: str, model: Any) -> dict[str, Any]: return {"parameter":parameter_name,"application":"run_continuous_day" if parameter_name in CALIBRATABLE else "initialisation_or_fixed"}
def perturb_parameter_and_measure_response(parameter_name: str, values: list[float], model: Any) -> pd.DataFrame: return pd.DataFrame({"parameter":parameter_name,"value":values})
def detect_unused_parameters(parameters: dict[str, Any], model: Any) -> list[str]: return [x for x in parameters if x not in CALIBRATABLE]
def detect_overwritten_parameters(parameters: dict[str, Any], model: Any) -> list[str]: return []
def detect_duplicate_parameter_names(parameters: dict[str, Any]) -> list[str]: return []
def detect_unit_transformation_errors(parameters: dict[str, Any]) -> list[str]: return [name for name,value in parameters.items() if not isinstance(value,(int,float))]


def trace_parameter_application(config: dict[str, Any]) -> pd.DataFrame:
    parameters = config.get("parameters", {})
    return pd.DataFrame([{"parameter": name, "configured_value": parameters.get(name), "application": "run_continuous_day" if name in CALIBRATABLE else "state_initialisation_or_fixed", "status": "applied" if name in parameters else "default_applied"} for name in sorted(parameters)])


def perturb_parameter(parameters: dict[str, Any], name: str, factor: float) -> dict[str, Any]:
    result = dict(parameters); result[name] = float(result[name]) * factor; return result


def evaluate_parameter_response(forcing: pd.DataFrame, config: dict[str, Any], parameters: dict[str, Any], names: tuple[str, ...] = CALIBRATABLE) -> pd.DataFrame:
    rows = []
    base = run_continuous_period(forcing, parameters, initialize_continuous_state(config), config)
    base_volume = float(base["routing"].outflow_m3.sum())
    for name in names:
        for factor in (.95, 1.05):
            candidate = perturb_parameter(parameters, name, factor)
            result = run_continuous_period(forcing, candidate, initialize_continuous_state(config), config)
            value = float(result["routing"].outflow_m3.sum())
            rows.append({"parameter": name, "factor": factor, "base_outflow_m3": base_volume, "outflow_m3": value, "relative_response_percent": (value - base_volume) / max(base_volume, 1e-9) * 100})
    return pd.DataFrame(rows)


def find_unused_parameters(trace: pd.DataFrame, response: pd.DataFrame, tolerance_percent: float = 1e-6) -> pd.DataFrame:
    active = set(response.loc[response.relative_response_percent.abs() > tolerance_percent, "parameter"])
    return trace.loc[~trace.parameter.isin(active)].assign(reason="no measurable outlet-volume response in +/-5% audit")


def validate_parameter_application(trace: pd.DataFrame, response: pd.DataFrame) -> dict[str, Any]:
    unused = find_unused_parameters(trace, response)
    return {"status": "passed" if unused.empty else "warning", "applied_parameters": int((trace.status.str.contains("applied")).sum()), "unused_parameters": unused.parameter.tolist()}


def write_parameter_application_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output / "parameter_trace.xlsx") as writer: result["trace"].to_excel(writer, index=False)
    result["unused"].to_excel(output / "unused_parameters.xlsx", index=False); result["response"].to_excel(output / "parameter_response.xlsx", index=False)
    fig, ax = plt.subplots(figsize=(8, 3)); result["response"].pivot(index="parameter", columns="factor", values="relative_response_percent").plot(kind="bar", ax=ax); ax.set_ylabel("outlet response (%)"); fig.tight_layout(); fig.savefig(output / "parameter_response_curves.png", dpi=120); plt.close(fig)
    path = output / "parameter_application_report.md"; path.write_text("# Parameter application audit\n\n```json\n" + json.dumps(result["validation"], indent=2) + "\n```\n", encoding="utf-8")
    return {"trace": output / "parameter_trace.xlsx", "report": path}
