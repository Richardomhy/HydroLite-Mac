from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CaseConfig:
    name: str
    time_step_hours: float
    input_dir: Path
    output_dir: Path
    rainfall_csv: Path
    subcatchments_csv: Path
    reaches_csv: Path


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
    if not isinstance(inputs, dict) or not isinstance(outputs, dict) or not isinstance(model, dict):
        raise ValueError("Case YAML sections inputs, outputs, and model must be mappings.")

    input_dir = _resolve(base_dir, _require(inputs, "directory", "inputs"))
    output_dir = _resolve(base_dir, _require(outputs, "directory", "outputs"))
    data_raw_dir = (base_dir / "data_raw").resolve()
    if _is_inside(output_dir, data_raw_dir):
        raise ValueError("outputs.directory must not point inside data_raw; raw data is read-only.")

    time_step_hours = float(_require(model, "time_step_hours", "model"))
    if time_step_hours <= 0:
        raise ValueError("model.time_step_hours must be positive.")

    return CaseConfig(
        name=str(_require(raw, "name", "root")),
        time_step_hours=time_step_hours,
        input_dir=input_dir,
        output_dir=output_dir,
        rainfall_csv=_resolve(input_dir, _require(inputs, "rainfall", "inputs")),
        subcatchments_csv=_resolve(input_dir, _require(inputs, "subcatchments", "inputs")),
        reaches_csv=_resolve(input_dir, _require(inputs, "reaches", "inputs")),
    )
