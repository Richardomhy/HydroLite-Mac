from __future__ import annotations

from pathlib import Path
import os
import signal
import subprocess
import time
from typing import Sequence


_PROCESSES: dict[int, subprocess.Popen] = {}


def start_managed_process(command: Sequence[str], cwd: str | Path, env: dict[str, str] | None, stdout_path: str | Path, stderr_path: str | Path) -> int:
    if not isinstance(command, (list, tuple)) or not command or not all(isinstance(item, str) for item in command):
        raise ValueError("Managed command must be a non-empty string array.")
    stdout = Path(stdout_path); stderr = Path(stderr_path)
    stdout.parent.mkdir(parents=True, exist_ok=True); stderr.parent.mkdir(parents=True, exist_ok=True)
    out_handle = stdout.open("w", encoding="utf-8")
    err_handle = stderr.open("w", encoding="utf-8")
    process = subprocess.Popen(list(command), cwd=Path(cwd), env={**os.environ, **(env or {})}, stdout=out_handle, stderr=err_handle, text=True, start_new_session=True, shell=False)
    process._hydrolite_handles = (out_handle, err_handle)  # type: ignore[attr-defined]
    _PROCESSES[process.pid] = process
    return process.pid


def inspect_managed_process(process_id: int) -> dict:
    process = _PROCESSES.get(int(process_id))
    return {"process_id": int(process_id), "managed": process is not None, "running": bool(process and process.poll() is None), "return_code": None if not process else process.poll()}


def wait_managed_process(process_id: int, timeout: float | None = None) -> int:
    process = _PROCESSES.get(int(process_id))
    if process is None:
        raise KeyError(f"Unknown managed process: {process_id}")
    try:
        return_code = process.wait(timeout=timeout)
    finally:
        if process.poll() is not None:
            for handle in getattr(process, "_hydrolite_handles", ()):
                handle.close()
    return return_code


def detect_child_processes(process_id: int) -> list[int]:
    try:
        output = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, check=False, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    pairs = [tuple(map(int, line.split())) for line in output.splitlines() if len(line.split()) == 2]
    children, frontier = [], [int(process_id)]
    while frontier:
        parent = frontier.pop()
        direct = [pid for pid, ppid in pairs if ppid == parent and pid not in children]
        children.extend(direct); frontier.extend(direct)
    return children


def terminate_process_tree(process_id: int) -> bool:
    process = _PROCESSES.get(int(process_id))
    if process is None:
        return False
    if process.poll() is None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.wait(timeout=5)
        except ProcessLookupError:
            pass
    for handle in getattr(process, "_hydrolite_handles", ()):
        handle.close()
    return True


def terminate_managed_process(process_id: int) -> bool:
    return terminate_process_tree(process_id)


def verify_process_stopped(process_id: int) -> bool:
    process = _PROCESSES.get(int(process_id))
    if process:
        return process.poll() is not None
    try:
        os.kill(int(process_id), 0)
    except (OSError, ProcessLookupError):
        return True
    return False


def list_hydrolite_processes() -> list[dict]:
    return [inspect_managed_process(pid) for pid in sorted(_PROCESSES)]


def cleanup_orphaned_runtime_processes(runtime_dir: str | Path) -> dict:
    stopped = []
    for pid, process in list(_PROCESSES.items()):
        if process.poll() is None:
            continue
        stopped.append(pid)
        _PROCESSES.pop(pid, None)
    return {"status": "passed", "orphaned_found": len(stopped), "cleaned_records": stopped, "runtime_dir": str(Path(runtime_dir))}
