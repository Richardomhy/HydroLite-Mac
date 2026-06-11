from __future__ import annotations

import argparse
import sys

from hydrolite.batch import run_batch
from hydrolite.compare import run_compare
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
