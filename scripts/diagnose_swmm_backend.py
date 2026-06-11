from __future__ import annotations

import importlib.metadata
import json
import platform
from pathlib import Path
import os
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIAGNOSIS_FILE = PROJECT_ROOT / "output" / "swmm_backend_diagnosis.txt"
DEMO_INP = PROJECT_ROOT / "data_raw" / "swmm" / "demo.inp"


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _run_code(code: str, *args: str, timeout: int = 30) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
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


def _import_check(module: str) -> dict[str, object]:
    return _run_code(f"import {module}; print('ok')")


def _direct_run(inp_file: Path) -> dict[str, object]:
    code = """
from pathlib import Path
import sys
from swmm_api import swmm5_run

inp = Path(sys.argv[1])
rpt = Path(sys.argv[2])
out = Path(sys.argv[3])
swmm5_run(inp, rpt, out)
print("ok")
"""
    return _run_code(
        code,
        str(inp_file),
        str(PROJECT_ROOT / "output" / "swmm_backend_direct.rpt"),
        str(PROJECT_ROOT / "output" / "swmm_backend_direct.out"),
        timeout=60,
    )


def build_report() -> str:
    DIAGNOSIS_FILE.parent.mkdir(parents=True, exist_ok=True)
    import_pyswmm = _import_check("pyswmm")
    import_toolkit = _import_check("swmm.toolkit")
    import_swmm_api = _import_check("swmm_api")
    direct_run = _direct_run(DEMO_INP)

    report = {
        "python_version": sys.version.replace("\n", " "),
        "python_executable": sys.executable,
        "macos_version": platform.mac_ver()[0],
        "cpu_architecture": platform.machine(),
        "is_conda_environment": bool(os.environ.get("CONDA_PREFIX")),
        "conda_prefix": os.environ.get("CONDA_PREFIX", ""),
        "pyswmm_version": _version("pyswmm"),
        "swmm_toolkit_version": _version("swmm-toolkit"),
        "swmm_api_version": _version("swmm_api"),
        "swmm_api_hyphen_version": _version("swmm-api"),
        "can_import_pyswmm": import_pyswmm["return_code"] == 0,
        "can_import_swmm_toolkit": import_toolkit["return_code"] == 0,
        "can_import_swmm_api": import_swmm_api["return_code"] == 0,
        "import_pyswmm": import_pyswmm,
        "import_swmm_toolkit": import_toolkit,
        "import_swmm_api": import_swmm_api,
        "demo_inp": str(DEMO_INP),
        "can_direct_run_demo_inp": direct_run["return_code"] == 0,
        "direct_run": direct_run,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    DIAGNOSIS_FILE.write_text(text + "\n", encoding="utf-8")
    return text


def main() -> int:
    text = build_report()
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

