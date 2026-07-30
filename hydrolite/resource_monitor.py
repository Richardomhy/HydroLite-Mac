from __future__ import annotations

from pathlib import Path
import os
import shutil


def inspect_disk_space(path: str | Path) -> dict:
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root)
    return {"path": str(root), "total_bytes": usage.total, "free_bytes": usage.free, "used_bytes": usage.used, "writable": os.access(root, os.W_OK)}


def inspect_memory() -> dict:
    page = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 0
    pages = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else 0
    return {"total_bytes": page * pages if page and pages else None, "backend": "stdlib"}


def inspect_cpu() -> dict:
    return {"logical_cpu_count": os.cpu_count(), "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None}


def estimate_task_storage(task_spec) -> int:
    limits = getattr(task_spec, "resource_limits", None)
    return int(getattr(limits, "estimated_storage_mb", 10) * 1024 * 1024)


def estimate_run_storage(run_plan: dict) -> int:
    return sum(int(task.get("estimated_storage_mb", 10) * 1024 * 1024) for task in run_plan.get("tasks", []))


def validate_resource_requirements(run_plan: dict) -> dict:
    target = run_plan.get("run_dir") or "."
    disk = inspect_disk_space(target)
    required = estimate_run_storage(run_plan)
    status = "passed" if disk["writable"] and disk["free_bytes"] > required else "failed"
    return {"status": status, "required_bytes": required, "disk": disk}


def monitor_process_resources(process_id: int) -> dict:
    return {"process_id": process_id, "status": "unavailable_without_psutil", "cpu_percent": None, "memory_bytes": None}


def write_resource_report(output_dir: str | Path, result: dict) -> Path:
    import json
    path = Path(output_dir) / "resource_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return path
