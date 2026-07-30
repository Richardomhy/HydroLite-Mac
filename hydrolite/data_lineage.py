from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import subprocess

import pandas as pd

from hydrolite.workspace import calculate_file_checksum


def _root(workspace_dir: str | Path) -> Path:
    return Path(workspace_dir).expanduser().resolve()


def _records_path(workspace_dir: str | Path) -> Path:
    path = _root(workspace_dir) / "lineage" / "lineage_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read(workspace_dir: str | Path) -> list[dict[str, Any]]:
    path = _records_path(workspace_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def _write(workspace_dir: str | Path, records: list[dict[str, Any]]) -> Path:
    path = _records_path(workspace_dir)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def _version() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=3).stdout.strip() or "unavailable"
    except Exception:
        return "unavailable"


def create_lineage_record(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "upload",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "code_version": _version(),
        "parent_id": None,
        "child_id": dataset["dataset_id"],
        "source_checksum": dataset.get("checksum"),
        "output_checksum": dataset.get("checksum"),
        "parameters": {},
        "warnings": dataset.get("warnings", []),
        "operator": "user_upload",
        "reproducible_command": f"python -m hydrolite data upload <file> <workspace>",
    }


def add_lineage_operation(parent_id: str, child_id: str, operation: str, workspace_dir: str | Path | None = None, **metadata: Any) -> dict[str, Any]:
    record = {
        "operation": operation,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "code_version": _version(),
        "parent_id": parent_id,
        "child_id": child_id,
        "source_checksum": metadata.get("source_checksum"),
        "output_checksum": metadata.get("output_checksum"),
        "parameters": metadata.get("parameters", {}),
        "warnings": metadata.get("warnings", []),
        "operator": metadata.get("operator", "hydrolite"),
        "reproducible_command": metadata.get("reproducible_command", ""),
    }
    if workspace_dir is not None:
        records = _read(workspace_dir)
        records.append(record)
        _write(workspace_dir, records)
    return record


def list_dataset_parents(dataset_id: str, workspace_dir: str | Path | None = None) -> list[str]:
    return sorted({row["parent_id"] for row in _read(workspace_dir) if row.get("child_id") == dataset_id and row.get("parent_id")}) if workspace_dir else []


def list_dataset_children(dataset_id: str, workspace_dir: str | Path | None = None) -> list[str]:
    return sorted({row["child_id"] for row in _read(workspace_dir) if row.get("parent_id") == dataset_id}) if workspace_dir else []


def validate_lineage_graph(workspace_dir: str | Path) -> dict[str, Any]:
    records = _read(workspace_dir)
    edges = [(row.get("parent_id"), row.get("child_id")) for row in records if row.get("parent_id")]
    graph: dict[str, list[str]] = {}
    for parent, child in edges:
        graph.setdefault(parent, []).append(child)
    visiting, visited = set(), set()

    def visit(node: str) -> bool:
        if node in visiting:
            return False
        if node in visited:
            return True
        visiting.add(node)
        if not all(visit(child) for child in graph.get(node, [])):
            return False
        visiting.remove(node)
        visited.add(node)
        return True

    acyclic = all(visit(node) for node in list(graph))
    return {"status": "passed" if acyclic else "failed", "record_count": len(records), "edge_count": len(edges), "acyclic": acyclic, "records": records}


def write_lineage_manifest(workspace_dir: str | Path) -> Path:
    return _write(workspace_dir, _read(workspace_dir))


def write_lineage_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    xlsx_path = output / "lineage_summary.xlsx"
    md_path = output / "lineage_report.md"
    pd.DataFrame(result.get("records", [])).to_excel(xlsx_path, index=False)
    md_path.write_text(f"# Data Lineage\n\n- Status: `{result['status']}`\n- Records: `{result['record_count']}`\n- Acyclic: `{result['acyclic']}`\n", encoding="utf-8")
    return {"xlsx": xlsx_path, "markdown": md_path}
