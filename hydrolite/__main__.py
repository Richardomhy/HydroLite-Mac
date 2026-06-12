from __future__ import annotations

import argparse
from pathlib import Path
import sys

from hydrolite.batch import run_batch
from hydrolite.compare import run_compare
from hydrolite.gee.export import (
    create_gee_data_plan,
    write_gee_summary_outputs,
    write_hydrolite_gee_outputs,
)
from hydrolite.gee.diagnostics import build_gee_diagnosis
from hydrolite.openhydronet.diagnostics import build_openhydronet_diagnosis
from hydrolite.openhydronet.runner import run_openhydronet_prepare_inputs, run_openhydronet_smoke
from hydrolite.runner import run_case
from hydrolite.validate import validate_target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hydrolite")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a HydroLite YAML case.")
    run_parser.add_argument("case_file", help="Path to YAML case file, e.g. cases/demo.yaml")

    batch_parser = subparsers.add_parser("batch", help="Run all HydroLite YAML cases in a directory.")
    batch_parser.add_argument("cases_dir", help="Directory containing .yaml and .yml case files.")

    compare_parser = subparsers.add_parser("compare", help="Compare HydroLite scenario outputs.")
    compare_parser.add_argument("output_dir", help="Output directory containing scenario result folders.")

    validate_parser = subparsers.add_parser("validate", help="Validate a HydroLite YAML case or cases directory.")
    validate_parser.add_argument("target", help="Path to a case YAML file or a directory containing cases.")

    gee_parser = subparsers.add_parser("gee", help="GEE data center commands.")
    gee_subparsers = gee_parser.add_subparsers(dest="gee_command", required=True)
    gee_subparsers.add_parser("diagnose", help="Diagnose local Google Earth Engine availability.")
    gee_plan = gee_subparsers.add_parser("plan", help="Write a GEE data plan workbook.")
    gee_plan.add_argument("config", help="Path to GEE YAML config.")
    gee_summary = gee_subparsers.add_parser("summarize", help="Write GEE basin summary outputs.")
    gee_summary.add_argument("config", help="Path to GEE YAML config.")
    gee_inputs = gee_subparsers.add_parser("hydrolite-inputs", help="Generate HydroLite inputs from GEE outputs.")
    gee_inputs.add_argument("config", help="Path to GEE YAML config.")

    openhydronet_parser = subparsers.add_parser("openhydronet", help="OpenHydroNet AI flood forecasting commands.")
    openhydronet_subparsers = openhydronet_parser.add_subparsers(dest="openhydronet_command", required=True)
    openhydronet_subparsers.add_parser("diagnose", help="Diagnose OpenHydroNet external repository and environment.")
    openhydronet_smoke = openhydronet_subparsers.add_parser("smoke", help="Run OpenHydroNet smoke test only.")
    openhydronet_smoke.add_argument("config", help="Path to OpenHydroNet YAML config.")
    openhydronet_prepare = openhydronet_subparsers.add_parser(
        "prepare-inputs", help="Prepare OpenHydroNet-ready input package."
    )
    openhydronet_prepare.add_argument("config", help="Path to OpenHydroNet YAML config.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        outputs = run_case(args.case_file)
        print(f"HydroLite run complete. Outputs written to: {outputs.output_dir}")
        return 0
    if args.command == "batch":
        summary_path, rows, failed_cases = run_batch(args.cases_dir)
        success_count = sum(1 for row in rows if row["status"] == "success")
        print(
            f"HydroLite batch complete. success={success_count}, "
            f"failed={len(failed_cases)}. Summary written to: {summary_path}"
        )
        if failed_cases:
            print("Failed cases:")
            for case_file in failed_cases:
                print(f"- {case_file}")
            return 1
        return 0
    if args.command == "compare":
        outputs = run_compare(args.output_dir)
        print(f"HydroLite comparison complete. Outputs written to: {outputs.output_dir}")
        return 0
    if args.command == "validate":
        result = validate_target(args.target)
        print(f"HydroLite validation complete. Outputs written to: {result.outputs.output_dir}")
        if result.has_fatal_errors:
            print("Validation failed with fatal errors.")
            return 1
        if not result.warnings.empty:
            print("Validation passed with warnings.")
        else:
            print("Validation passed.")
        return 0
    if args.command == "gee":
        if args.gee_command == "diagnose":
            diagnosis = build_gee_diagnosis()
            output = Path("output/gee_diagnosis.txt").resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            import json

            output.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"GEE diagnosis written to: {output}")
            return 0
        if args.gee_command == "plan":
            plan = create_gee_data_plan(args.config)
            output = Path("output/gee/gee_data_plan.xlsx").resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            plan.to_excel(output, index=False)
            print(f"GEE data plan written to: {output}")
            return 0
        if args.gee_command == "summarize":
            outputs = write_gee_summary_outputs(args.config)
            print(f"GEE summary written to: {outputs['gee_summary_xlsx']}")
            return 0
        if args.gee_command == "hydrolite-inputs":
            outputs = write_hydrolite_gee_outputs(args.config)
            print(f"GEE HydroLite inputs written to: {outputs['gee_to_hydrolite_report_md'].parent}")
            return 0
    if args.command == "openhydronet":
        if args.openhydronet_command == "diagnose":
            diagnosis = build_openhydronet_diagnosis()
            output = Path("output/openhydronet_diagnosis.txt").resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            import json

            output.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"OpenHydroNet diagnosis written to: {output}")
            return 0
        if args.openhydronet_command == "smoke":
            result = run_openhydronet_smoke(args.config)
            print(f"OpenHydroNet smoke status: {result['status']}")
            print(f"Summary written to: {result['summary_path']}")
            print(f"Report written to: {result['report_path']}")
            return 0
        if args.openhydronet_command == "prepare-inputs":
            result = run_openhydronet_prepare_inputs(args.config)
            print(f"OpenHydroNet input package status: {result['status']}")
            print(f"Inputs written to: {result['output_dir']}")
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
