from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd

from hydrolite.event_dataset import load_event_source
from hydrolite.flood_events import build_event_catalog


def _coverage(frame: pd.DataFrame, value_names: tuple[str, ...]) -> float:
    column = next((name for name in value_names if name in frame), None)
    return float(pd.to_numeric(frame[column], errors="coerce").notna().mean()) if column and len(frame) else 0.0


def _level(real_qualified: int, validation_count: int, test_count: int) -> str:
    if real_qualified == 0:
        return "framework_ready_real_data_missing"
    if real_qualified <= 2:
        return "limited_event_hindcast"
    if real_qualified < 5 or validation_count == 0:
        return "multi_event_hindcast_no_independent_test"
    if real_qualified < 8 or test_count == 0:
        return "multi_event_validated"
    return "multi_event_tested"


def assess_hindcast_readiness(workspace_dir: str | Path) -> dict[str, Any]:
    root = Path(workspace_dir)
    source = load_event_source(root)
    catalog = build_event_catalog(root) if not source["rainfall"].empty else pd.DataFrame()
    qualified = catalog.get("quality_status", pd.Series(dtype=str)).isin(["accepted", "accepted_with_warnings"])
    synthetic = catalog.get("observed_is_synthetic", pd.Series(False, index=catalog.index)).astype(bool)
    qualified_count = int(qualified.sum())
    real_qualified = int((qualified & ~synthetic).sum())
    split_path = Path("output/hindcast_validation/splits/event_split.yaml")
    validation_count = test_count = 0
    if split_path.exists():
        import yaml
        split = yaml.safe_load(split_path.read_text(encoding="utf-8")) or {}
        validation_count, test_count = len(split.get("validation", [])), len(split.get("test", []))
    level = _level(real_qualified, validation_count, test_count)
    rain_coverage = _coverage(source["rainfall"], ("rainfall_mm", "rain_mm", "precipitation_mm"))
    flow_coverage = _coverage(source["flow"], ("flow_cms", "observed_streamflow_m3s"))
    stage_coverage = _coverage(source["stage"], ("stage_m", "water_level_m"))
    required_present = not source["rainfall"].empty and not source["flow"].empty and not source["stations"].empty
    status = "ready_with_warnings" if required_present and qualified_count else "missing_data"
    return {
        "status": status,
        "validation_level": level,
        "demo_validation_level": "synthetic_demo" if qualified_count and real_qualified == 0 else "not_applicable",
        "event_count": int(len(catalog)),
        "qualified_event_count": qualified_count,
        "real_qualified_event_count": real_qualified,
        "rainfall_coverage": rain_coverage,
        "streamflow_coverage": flow_coverage,
        "stage_coverage": stage_coverage,
        "station_count": int(source["stations"].get("station_id", pd.Series(dtype=str)).nunique()),
        "independent_validation": validation_count > 0 and real_qualified >= 5,
        "independent_test": test_count > 0 and real_qualified >= 8,
        "water_balance_gate": "required_per_event",
        "operational_readiness": False,
        "warnings": ["Synthetic events are excluded from real validation metrics."] if real_qualified == 0 and qualified_count else [],
        "required_templates": [
            "templates/data_upload/flood_event_catalog.csv",
            "templates/data_upload/data_assimilation_observations.csv",
        ],
    }


def assess_assimilation_readiness(workspace_dir: str | Path) -> dict[str, Any]:
    source = load_event_source(workspace_dir)
    base = assess_hindcast_readiness(workspace_dir)
    observations = source["assimilation"]
    available = not observations.empty and any(name in observations for name in ("flow_cms", "stage_m", "value"))
    return {**base, "status": "ready_with_warnings" if available else "missing_data", "assimilation_observations": int(len(observations)), "observation_error_required": True}


def assess_multi_event_calibration_readiness(workspace_dir: str | Path) -> dict[str, Any]:
    base = assess_hindcast_readiness(workspace_dir)
    base["status"] = "ready_with_warnings" if base["qualified_event_count"] >= 3 else "limited"
    base["minimum_calibration_events"] = 3
    return base


def assess_ml_validation_readiness(workspace_dir: str | Path) -> dict[str, Any]:
    source = load_event_source(workspace_dir)
    base = assess_hindcast_readiness(workspace_dir)
    valid_steps = int(source["flow"].get("flow_cms", pd.Series(dtype=float)).notna().sum())
    real_ready = base["real_qualified_event_count"] >= 5 and valid_steps >= 500 and base["independent_validation"]
    lstm_ready = base["real_qualified_event_count"] >= 8 and valid_steps >= 1000 and base["independent_test"]
    return {**base, "valid_time_steps": valid_steps, "real_training_ready": real_ready, "lstm_real_training_ready": lstm_ready, "feature_leakage_check": "required"}


def assess_operational_readiness(workspace_dir: str | Path) -> dict[str, Any]:
    base = assess_hindcast_readiness(workspace_dir)
    return {**base, "status": "blocked", "operational_candidate": False, "operational_verified": False, "reason": "No formal real-time operational record or forecast-input monitoring."}


def write_validation_readiness_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "hindcast_readiness.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    paths = {"json": json_path}
    for language, title in (("zh", "多事件洪水验证就绪度"), ("en", "Multi-event Hindcast Readiness")):
        path = output / f"hindcast_readiness_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Status: `{result['status']}`\n"
            f"- Validation level: `{result['validation_level']}`\n"
            f"- Qualified events: `{result['qualified_event_count']}`; real qualified events: `{result['real_qualified_event_count']}`\n"
            f"- Rainfall/flow/stage coverage: `{result['rainfall_coverage']:.1%}` / `{result['streamflow_coverage']:.1%}` / `{result['stage_coverage']:.1%}`\n"
            "- Synthetic demo results are excluded from real-data validation and operational claims.\n",
            encoding="utf-8",
        )
        paths[language] = path
    return paths
