from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import shutil

import pandas as pd

from hydrolite.hec_hms import detect_hec_hms_installations
from hydrolite.runtime_mode import detect_runtime_mode


def create_hms_hindcast_project(event: dict[str, Any], base_project: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source = Path(base_project)
    if source.is_dir():
        for path in source.iterdir():
            if path.is_file() and path.suffix.lower() in {".hms", ".basin", ".met", ".control", ".run", ".gage"}:
                shutil.copy2(path, output / path.name)
    return {"event_id": event["event_id"], "project_dir": str(output), "base_project": str(source), "base_project_modified": False}


def write_hms_event_rainfall(event: dict[str, Any], project_dir: str | Path) -> Path:
    path = Path(project_dir) / "hydrolite_event_rainfall_manifest.json"
    path.write_text(json.dumps({"event_id": event["event_id"], "source": "standardized event rainfall", "dss_required": True}, indent=2), encoding="utf-8")
    return path


def set_hms_event_control_window(event: dict[str, Any], project_dir: str | Path) -> Path:
    path = Path(project_dir) / "hydrolite_control_window.json"
    path.write_text(json.dumps({"start": str(event["warmup_start"]), "end": str(event["analysis_end"])}, indent=2), encoding="utf-8")
    return path


def set_hms_initial_conditions(event: dict[str, Any], project_dir: str | Path) -> Path:
    path = Path(project_dir) / "hydrolite_initial_conditions.json"
    path.write_text(json.dumps({"event_id": event["event_id"], "status": "requires_verified_hms_mapping"}, indent=2), encoding="utf-8")
    return path


def run_hms_hindcast_event(event: dict[str, Any], project_dir: str | Path, timeout: int = 120) -> dict[str, Any]:
    if timeout > 120:
        raise ValueError("HEC-HMS event timeout must not exceed 120 seconds.")
    mode = detect_runtime_mode()["mode"]
    installations = detect_hec_hms_installations()
    if mode != "local_full":
        return {"event_id": event["event_id"], "status": "skipped", "reason": f"HEC-HMS requires local_full mode; current mode={mode}.", "timeout": timeout}
    if not any(item.get("exists") for item in installations):
        return {"event_id": event["event_id"], "status": "skipped", "reason": "HEC-HMS executable unavailable.", "timeout": timeout}
    return {"event_id": event["event_id"], "status": "blocked_gate", "reason": "Per-event DSS/control mapping requires a verified base project; Reservoir remains blocked_gate.", "timeout": timeout}


def extract_hms_hindcast_results(event: dict[str, Any], project_dir: str | Path) -> dict[str, Any]:
    return {"event_id": event["event_id"], "status": "missing", "timeseries": pd.DataFrame(), "reason": "No completed event DSS was produced."}


def validate_hms_hindcast_result(result: dict[str, Any]) -> dict[str, Any]:
    return {"status": "passed" if result.get("status") == "success" else "skipped", "reason": result.get("reason", "")}


def run_hms_hindcast_batch(events: Any, config: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for event in events.to_dict("records") if isinstance(events, pd.DataFrame) else events:
        rows.append(run_hms_hindcast_event(event, config.get("project_dir", ""), min(int(config.get("timeout", 120)), 120)))
    return {"status": "success" if any(row["status"] == "success" for row in rows) else "skipped", "events": pd.DataFrame(rows)}


def write_hms_hindcast_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    events = result.get("events", pd.DataFrame())
    xlsx = output / "hec_hms_event_summary.xlsx"
    events.to_excel(xlsx, index=False)
    report = output / "hec_hms_hindcast_report.md"
    report.write_text(
        "# HEC-HMS Multi-event Hindcast\n\n"
        f"- Status: `{result.get('status')}`\n"
        "- HEC-HMS is optional, local_full only, isolated per event, and never treated as observation.\n"
        "- HEC-HMS Reservoir remains `blocked_gate`.\n",
        encoding="utf-8",
    )
    return {"xlsx": xlsx, "report": report}
