from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import csv


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


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _series_rows(series: dict[Any, Any], id_column: str, object_id: str, value_column: str) -> list[dict[str, Any]]:
    return [
        {
            "datetime": key.isoformat() if hasattr(key, "isoformat") else str(key),
            id_column: object_id,
            value_column: value,
        }
        for key, value in series.items()
    ]


def _integrate(values: list[float], times: list[Any]) -> float:
    if len(values) < 2 or len(times) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(values)):
        try:
            dt = (times[i] - times[i - 1]).total_seconds()
        except Exception:
            dt = 0.0
        total += (float(values[i - 1]) + float(values[i])) / 2.0 * dt
    return total


def _extract_results(out: Path, rpt: Path, result_dir: Path, run_status: str, backend_used: str) -> dict[str, Any]:
    node_csv = result_dir / "node_depth_timeseries.csv"
    link_csv = result_dir / "link_flow_timeseries.csv"
    system_csv = result_dir / "system_timeseries.csv"
    extraction_errors: list[str] = []
    node_rows: list[dict[str, Any]] = []
    link_rows: list[dict[str, Any]] = []
    system_rows: list[dict[str, Any]] = []
    kpis: dict[str, Any] = {
        "run_status": run_status,
        "backend_used": backend_used,
        "max_node_depth": None,
        "max_link_flow": None,
        "total_flooding_volume": None,
        "total_outflow_volume": None,
        "node_count": 0,
        "link_count": 0,
        "report_file": str(rpt),
        "output_file": str(out),
    }

    try:
        from pyswmm import Output
        from swmm.toolkit.shared_enum import LinkAttribute, NodeAttribute, SystemAttribute

        with Output(str(out)) as output:
            times = list(output.times)
            kpis["node_count"] = len(output.nodes)
            kpis["link_count"] = len(output.links)

            for node_id in output.nodes:
                series = output.node_series(node_id, NodeAttribute.INVERT_DEPTH)
                node_rows.extend(_series_rows(series, "node_id", node_id, "depth"))
            for link_id in output.links:
                series = output.link_series(link_id, LinkAttribute.FLOW_RATE)
                link_rows.extend(_series_rows(series, "link_id", link_id, "flow"))

            system_series = {
                "runoff": output.system_series(SystemAttribute.RUNOFF_FLOW),
                "flooding": output.system_series(SystemAttribute.FLOOD_LOSSES),
                "outflow": output.system_series(SystemAttribute.OUTFALL_FLOWS),
                "storage": output.system_series(SystemAttribute.VOLUME_STORED),
            }
            for dt in times:
                system_rows.append(
                    {
                        "datetime": dt.isoformat() if hasattr(dt, "isoformat") else str(dt),
                        "runoff": system_series["runoff"].get(dt),
                        "flooding": system_series["flooding"].get(dt),
                        "outflow": system_series["outflow"].get(dt),
                        "storage": system_series["storage"].get(dt),
                    }
                )

            node_depths = [float(row["depth"]) for row in node_rows if row["depth"] is not None]
            link_flows = [float(row["flow"]) for row in link_rows if row["flow"] is not None]
            flood_values = [float(system_series["flooding"].get(dt) or 0.0) for dt in times]
            outflow_values = [float(system_series["outflow"].get(dt) or 0.0) for dt in times]
            kpis["max_node_depth"] = max(node_depths) if node_depths else None
            kpis["max_link_flow"] = max(link_flows) if link_flows else None
            kpis["total_flooding_volume"] = _integrate(flood_values, times)
            kpis["total_outflow_volume"] = _integrate(outflow_values, times)
    except Exception as exc:
        extraction_errors.append(str(exc))

    _write_csv(node_csv, node_rows, ["datetime", "node_id", "depth"])
    _write_csv(link_csv, link_rows, ["datetime", "link_id", "flow"])
    _write_csv(system_csv, system_rows, ["datetime", "runoff", "flooding", "outflow", "storage"])
    return {
        "node_depth_timeseries_csv": str(node_csv),
        "link_flow_timeseries_csv": str(link_csv),
        "system_timeseries_csv": str(system_csv),
        "kpis": kpis,
        "result_extraction_errors": extraction_errors,
    }


def run_solver(inp: Path, rpt: Path, out: Path, summary: Path) -> tuple[int, dict[str, object]]:
    summary.parent.mkdir(parents=True, exist_ok=True)
    if not inp.exists():
        payload = {
            "run_status": "failed",
            "backend_used": "",
            "backend_attempts": [],
            "return_code": 1,
            "error_message": f"inp file not found: {inp}",
            "inp": str(inp),
            "rpt": str(rpt),
            "out": str(out),
            "report_file_exists": rpt.exists(),
            "output_file_exists": out.exists(),
            "node_depth_timeseries_csv": str(summary.parent / "node_depth_timeseries.csv"),
            "link_flow_timeseries_csv": str(summary.parent / "link_flow_timeseries.csv"),
            "system_timeseries_csv": str(summary.parent / "system_timeseries.csv"),
            "kpis": {
                "run_status": "failed",
                "backend_used": "",
                "max_node_depth": None,
                "max_link_flow": None,
                "total_flooding_volume": None,
                "total_outflow_volume": None,
                "node_count": 0,
                "link_count": 0,
                "report_file": str(rpt),
                "output_file": str(out),
            },
            "result_extraction_errors": [],
        }
        _write_csv(summary.parent / "node_depth_timeseries.csv", [], ["datetime", "node_id", "depth"])
        _write_csv(summary.parent / "link_flow_timeseries.csv", [], ["datetime", "link_id", "flow"])
        _write_csv(
            summary.parent / "system_timeseries.csv",
            [],
            ["datetime", "runoff", "flooding", "outflow", "storage"],
        )
        summary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 1, payload
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
    extraction = _extract_results(out, rpt, summary.parent, "success" if success else "failed", backend_used)
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
        **extraction,
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
