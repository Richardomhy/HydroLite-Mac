from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SwmmCouplingConfig:
    enabled: bool = False
    source_flow_csv: Path | None = None
    source_time_column: str = "time"
    source_flow_column: str = "outflow_cms"
    target_node: str = ""
    inflow_name: str = "HYDROLITE_INFLOW"
    flow_unit: str = "CMS"


@dataclass(frozen=True)
class ObservedConfig:
    enabled: bool = False
    observed_streamflow_csv: Path | None = None
    time_column: str = "datetime"
    flow_column: str = "observed_streamflow_m3s"
    gauge_id_column: str = "gauge_id"


@dataclass(frozen=True)
class CaseConfig:
    name: str
    time_step_hours: float
    input_dir: Path
    output_dir: Path
    rainfall_csv: Path
    subcatchments_csv: Path
    reaches_csv: Path
    swmm_enabled: bool = False
    swmm_inp_file: Path | None = None
    swmm_coupling: SwmmCouplingConfig = SwmmCouplingConfig()
    observed: ObservedConfig = ObservedConfig()


def _resolve(base_dir: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def _require(mapping: dict[str, Any], key: str, section: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise ValueError(f"Case YAML missing required field: {section}.{key}")
    return mapping[key]


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def load_case(path: str | Path) -> CaseConfig:
    case_path = Path(path).expanduser().resolve()
    with case_path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError("Case YAML root must be a mapping.")

    base_dir = case_path.parent.parent if case_path.parent.name == "cases" else case_path.parent
    inputs = _require(raw, "inputs", "root")
    outputs = _require(raw, "outputs", "root")
    model = _require(raw, "model", "root")
    swmm = raw.get("swmm", {}) or {}
    observed = raw.get("observed", {}) or {}
    if not isinstance(inputs, dict) or not isinstance(outputs, dict) or not isinstance(model, dict):
        raise ValueError("Case YAML sections inputs, outputs, and model must be mappings.")
    if not isinstance(swmm, dict):
        raise ValueError("Case YAML section swmm must be a mapping when provided.")
    if not isinstance(observed, dict):
        raise ValueError("Case YAML section observed must be a mapping when provided.")
    coupling = swmm.get("coupling", {}) or {}
    if not isinstance(coupling, dict):
        raise ValueError("Case YAML section swmm.coupling must be a mapping when provided.")

    input_dir = _resolve(base_dir, _require(inputs, "directory", "inputs"))
    output_dir = _resolve(base_dir, _require(outputs, "directory", "outputs"))
    data_raw_dir = (base_dir / "data_raw").resolve()
    if _is_inside(output_dir, data_raw_dir):
        raise ValueError("outputs.directory must not point inside data_raw; raw data is read-only.")

    time_step_hours = float(_require(model, "time_step_hours", "model"))
    if time_step_hours <= 0:
        raise ValueError("model.time_step_hours must be positive.")
    swmm_enabled = bool(swmm.get("enabled", False))
    swmm_inp_file = _resolve(base_dir, _require(swmm, "inp_file", "swmm")) if swmm_enabled else None
    coupling_enabled = bool(coupling.get("enabled", False))
    swmm_coupling = SwmmCouplingConfig(
        enabled=coupling_enabled,
        source_flow_csv=_resolve(
            base_dir, coupling.get("source_flow_csv", f"output/{raw.get('name', case_path.stem)}/result_flow.csv")
        )
        if coupling_enabled
        else None,
        source_time_column=str(coupling.get("source_time_column", "time")),
        source_flow_column=str(coupling.get("source_flow_column", "outflow_cms")),
        target_node=str(coupling.get("target_node", "")),
        inflow_name=str(coupling.get("inflow_name", "HYDROLITE_INFLOW")),
        flow_unit=str(coupling.get("flow_unit", "CMS")),
    )
    observed_enabled = bool(observed.get("enabled", False))
    observed_config = ObservedConfig(
        enabled=observed_enabled,
        observed_streamflow_csv=_resolve(base_dir, _require(observed, "observed_streamflow_csv", "observed"))
        if observed_enabled
        else None,
        time_column=str(observed.get("time_column", "datetime")),
        flow_column=str(observed.get("flow_column", "observed_streamflow_m3s")),
        gauge_id_column=str(observed.get("gauge_id_column", "gauge_id")),
    )

    return CaseConfig(
        name=str(_require(raw, "name", "root")),
        time_step_hours=time_step_hours,
        input_dir=input_dir,
        output_dir=output_dir,
        rainfall_csv=_resolve(input_dir, _require(inputs, "rainfall", "inputs")),
        subcatchments_csv=_resolve(input_dir, _require(inputs, "subcatchments", "inputs")),
        reaches_csv=_resolve(input_dir, _require(inputs, "reaches", "inputs")),
        swmm_enabled=swmm_enabled,
        swmm_inp_file=swmm_inp_file,
        swmm_coupling=swmm_coupling,
        observed=observed_config,
    )
