from __future__ import annotations

import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output" / "swmm_env_test"
SUMMARY = OUTPUT_DIR / "external_solver_summary.json"


def _import_check(module: str) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [sys.executable, "-c", f"import {module}; print('ok')"],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        return {
            "return_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "return_code": "timeout",
            "stdout": exc.stdout or "",
            "stderr": str(exc),
        }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_inp = PROJECT_ROOT / "data_raw" / "swmm" / "demo.inp"
    inp = OUTPUT_DIR / "working.inp"
    shutil.copy2(source_inp, inp)
    rpt = OUTPUT_DIR / "model.rpt"
    out = OUTPUT_DIR / "model.out"

    solver = PROJECT_ROOT / "scripts" / "swmm_env" / "run_swmm_solver.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(solver),
            "--inp",
            str(inp),
            "--rpt",
            str(rpt),
            "--out",
            str(out),
            "--summary",
            str(SUMMARY),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    payload = {
        "python_version": sys.version.replace("\n", " "),
        "python_executable": sys.executable,
        "platform_machine": platform.machine(),
        "import_pyswmm": _import_check("pyswmm"),
        "import_swmm_toolkit": _import_check("swmm.toolkit"),
        "import_swmm_api": _import_check("swmm_api"),
        "run_return_code": completed.returncode,
        "run_stdout": completed.stdout.strip(),
        "run_stderr": completed.stderr.strip(),
        "report_file": str(rpt),
        "output_file": str(out),
        "report_file_exists": rpt.exists(),
        "output_file_exists": out.exists(),
        "external_solver_summary": str(SUMMARY),
    }
    if SUMMARY.exists():
        payload["external_solver_summary_json"] = json.loads(SUMMARY.read_text(encoding="utf-8"))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
