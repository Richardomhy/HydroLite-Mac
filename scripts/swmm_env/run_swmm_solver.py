from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def _run_code(backend_name: str, code: str, inp: Path, rpt: Path, out: Path) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code, str(inp), str(rpt), str(out)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        message = (completed.stderr or completed.stdout or "").strip()
        if completed.returncode != 0 and not message:
            message = f"{backend_name} exited with code {completed.returncode}"
        return {
            "backend_name": backend_name,
            "backend_available": completed.returncode != 127,
            "backend_status": "success" if completed.returncode == 0 else "failed",
            "return_code": completed.returncode,
            "error_message": message,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "backend_name": backend_name,
            "backend_available": True,
            "backend_status": "failed",
            "return_code": "timeout",
            "error_message": str(exc),
        }


def run_solver(inp: Path, rpt: Path, out: Path, summary: Path) -> tuple[int, dict[str, object]]:
    summary.parent.mkdir(parents=True, exist_ok=True)
    snippets = {
        "pyswmm": """
import sys
from pyswmm import Simulation

inp, rpt, out = sys.argv[1:4]
with Simulation(inp) as sim:
    for _ in sim:
        pass
""",
        "swmm-toolkit": """
import sys
from swmm.toolkit import solver

inp, rpt, out = sys.argv[1:4]
if hasattr(solver, "swmm_run"):
    solver.swmm_run(inp, rpt, out)
elif hasattr(solver, "run"):
    solver.run(inp, rpt, out)
else:
    raise RuntimeError("swmm.toolkit.solver has no supported run function")
""",
        "swmm_api": """
import sys
from swmm_api import swmm5_run

inp, rpt, out = sys.argv[1:4]
swmm5_run(inp, rpt, out)
""",
    }
    attempts: list[dict[str, object]] = []
    backend_used = ""
    for backend_name, code in snippets.items():
        attempt = _run_code(backend_name, code, inp, rpt, out)
        attempts.append(attempt)
        if attempt["backend_status"] == "success":
            backend_used = backend_name
            generated_rpt = inp.with_suffix(".rpt")
            generated_out = inp.with_suffix(".out")
            if not rpt.exists() and generated_rpt.exists():
                shutil.copy2(generated_rpt, rpt)
            if not out.exists() and generated_out.exists():
                shutil.copy2(generated_out, out)
            break

    success = bool(backend_used)
    payload = {
        "run_status": "success" if success else "failed",
        "backend_used": backend_used,
        "backend_attempts": attempts,
        "return_code": 0 if success else 1,
        "error_message": ""
        if success
        else "; ".join(
            f"{item['backend_name']}: {item['error_message'] or 'failed'}"
            for item in attempts
        ),
        "inp": str(inp),
        "rpt": str(rpt),
        "out": str(out),
        "report_file_exists": rpt.exists(),
        "output_file_exists": out.exists(),
    }
    summary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return (0 if success else 1), payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inp", required=True)
    parser.add_argument("--rpt", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code, payload = run_solver(
        Path(args.inp).expanduser().resolve(),
        Path(args.rpt).expanduser().resolve(),
        Path(args.out).expanduser().resolve(),
        Path(args.summary).expanduser().resolve(),
    )
    print(json.dumps(payload, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
