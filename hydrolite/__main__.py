from __future__ import annotations

import argparse
from pathlib import Path
import sys

from hydrolite.__version__ import __app_name__, __release_date__, __version__
from hydrolite.batch import run_batch
from hydrolite.beta import beta_checklist, beta_info, beta_smoke_local
from hydrolite.compare import run_compare
from hydrolite.data_templates import (
    export_all_data_templates,
    export_data_template,
    list_data_templates,
    validate_project_input_dataset,
    write_data_template_summary,
)
from hydrolite.export_report import (
    export_project_report_bundle,
    render_project_report_all,
    render_project_report_docx,
    render_project_report_html,
    render_project_report_markdown,
    render_project_report_pdf,
)
from hydrolite.gee.export import (
    create_gee_data_plan,
    write_gee_summary_outputs,
    write_hydrolite_gee_outputs,
)
from hydrolite.gee.diagnostics import build_gee_diagnosis
from hydrolite.healthcheck import build_healthcheck, healthcheck_status
from hydrolite.openhydronet.diagnostics import build_openhydronet_diagnosis
from hydrolite.openhydronet.runner import run_openhydronet_prepare_inputs, run_openhydronet_smoke
from hydrolite.project import (
    compare_project_outputs,
    create_project,
    export_project_package,
    project_info,
    run_project_batch,
    run_project_case,
    validate_project,
)
from hydrolite.qgis_bridge import (
    build_qgis_diagnosis,
    convert_geojson_to_reaches_csv,
    convert_geojson_to_subbasins_csv,
    convert_qgis_layers_to_hydrolite_inputs,
    create_project_from_qgis_outputs,
    detect_qgis_process_candidates,
    export_basin_boundary_geojson,
    infer_hydrolite_field_mapping,
    qgis_bridge_demo,
    qgis_export_attributes_csv,
    qgis_export_vector,
    qgis_layer_info,
    qgis_process_algorithms,
    qgis_process_version,
    qgis_validate_vector_layer,
    recommend_qgis_bridge_mode,
    run_qgis_project_workflow,
    validate_qgis_to_hydrolite_outputs,
    write_qgis_diagnosis,
)
from hydrolite.runner import run_case
from hydrolite.tutorial import (
    generate_demo_summary,
    get_demo_checklist,
    get_demo_steps,
    reset_demo_progress,
)
from hydrolite.validate import validate_target
from hydrolite.wizard import create_project_from_wizard, preview_wizard, validate_wizard_config


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

    subparsers.add_parser("version", help="Show HydroLite Studio version information.")
    subparsers.add_parser("healthcheck", help="Run HydroLite Studio release healthcheck.")
    subparsers.add_parser("roadmap", help="Show HydroLite Studio v0.7.0 roadmap document paths.")

    gee_parser = subparsers.add_parser("gee", help="GEE data center commands.")
    gee_subparsers = gee_parser.add_subparsers(dest="gee_command", required=True)
    gee_subparsers.add_parser("diagnose", help="Diagnose local Google Earth Engine availability.")
    gee_plan = gee_subparsers.add_parser("plan", help="Write a GEE data plan workbook.")
    gee_plan.add_argument("config", help="Path to GEE YAML config.")
    gee_summary = gee_subparsers.add_parser("summarize", help="Write GEE basin summary outputs.")
    gee_summary.add_argument("config", help="Path to GEE YAML config.")
    gee_inputs = gee_subparsers.add_parser("hydrolite-inputs", help="Generate HydroLite inputs from GEE outputs.")
    gee_inputs.add_argument("config", help="Path to GEE YAML config.")

    qgis_parser = subparsers.add_parser("qgis", help="QGIS Bridge feasibility diagnostics.")
    qgis_subparsers = qgis_parser.add_subparsers(dest="qgis_command", required=True)
    qgis_subparsers.add_parser("diagnose", help="Write QGIS Bridge diagnosis outputs.")
    qgis_subparsers.add_parser("paths", help="List qgis_process candidate paths.")
    qgis_subparsers.add_parser("recommend", help="Recommend QGIS Bridge integration mode.")
    qgis_subparsers.add_parser("version", help="Show qgis_process version.")
    qgis_algorithms = qgis_subparsers.add_parser("algorithms", help="List QGIS Processing algorithms.")
    qgis_algorithms.add_argument("--filter", default=None)
    qgis_layer_info_parser = qgis_subparsers.add_parser("layer-info", help="Read vector layer information.")
    qgis_layer_info_parser.add_argument("input_path")
    qgis_validate_layer = qgis_subparsers.add_parser("validate-layer", help="Validate a vector layer.")
    qgis_validate_layer.add_argument("input_path")
    qgis_export_vector_parser = qgis_subparsers.add_parser("export-vector", help="Export vector layer.")
    qgis_export_vector_parser.add_argument("input_path")
    qgis_export_vector_parser.add_argument("output_path")
    qgis_export_csv_parser = qgis_subparsers.add_parser("export-csv", help="Export vector attributes to CSV.")
    qgis_export_csv_parser.add_argument("input_path")
    qgis_export_csv_parser.add_argument("output_csv")
    qgis_subparsers.add_parser("demo", help="Run QGIS process bridge demo.")
    qgis_infer = qgis_subparsers.add_parser("infer-mapping", help="Infer HydroLite field mapping.")
    qgis_infer.add_argument("layer_path")
    qgis_infer.add_argument("target_template", choices=["subbasins", "reaches"])
    qgis_convert_subbasins = qgis_subparsers.add_parser("convert-subbasins", help="Convert GeoJSON to subbasins.csv.")
    qgis_convert_subbasins.add_argument("layer_path")
    qgis_convert_subbasins.add_argument("output_csv")
    qgis_convert_reaches = qgis_subparsers.add_parser("convert-reaches", help="Convert GeoJSON to reaches.csv.")
    qgis_convert_reaches.add_argument("layer_path")
    qgis_convert_reaches.add_argument("output_csv")
    qgis_export_basin = qgis_subparsers.add_parser("export-basin", help="Export basin boundary GeoJSON.")
    qgis_export_basin.add_argument("layer_path")
    qgis_export_basin.add_argument("output_geojson")
    qgis_to_hydrolite = qgis_subparsers.add_parser("to-hydrolite", help="Convert QGIS/GeoJSON layers to HydroLite inputs.")
    qgis_to_hydrolite.add_argument("subbasins_layer")
    qgis_to_hydrolite.add_argument("reaches_layer")
    qgis_to_hydrolite.add_argument("basin_layer")
    qgis_to_hydrolite.add_argument("output_dir")
    qgis_validate_hydrolite = qgis_subparsers.add_parser("validate-hydrolite", help="Validate converted HydroLite inputs.")
    qgis_validate_hydrolite.add_argument("output_dir")
    qgis_create_project = qgis_subparsers.add_parser("create-project", help="Create a HydroLite project from QGIS converted inputs.")
    qgis_create_project.add_argument("qgis_output_dir")
    qgis_create_project.add_argument("project_dir")
    qgis_create_project.add_argument("--rainfall-csv", default=None)
    qgis_create_project.add_argument("--project-name", default=None)
    qgis_project_workflow = qgis_subparsers.add_parser("project-workflow", help="Create and run a HydroLite project from QGIS converted inputs.")
    qgis_project_workflow.add_argument("qgis_output_dir")
    qgis_project_workflow.add_argument("project_dir")
    qgis_project_workflow.add_argument("--rainfall-csv", default=None)
    qgis_project_workflow.add_argument("--run-batch", action="store_true")
    qgis_project_workflow.add_argument("--run-compare", action="store_true")
    qgis_project_workflow.add_argument("--run-report", action="store_true")

    openhydronet_parser = subparsers.add_parser("openhydronet", help="OpenHydroNet AI flood forecasting commands.")
    openhydronet_subparsers = openhydronet_parser.add_subparsers(dest="openhydronet_command", required=True)
    openhydronet_subparsers.add_parser("diagnose", help="Diagnose OpenHydroNet external repository and environment.")
    openhydronet_smoke = openhydronet_subparsers.add_parser("smoke", help="Run OpenHydroNet smoke test only.")
    openhydronet_smoke.add_argument("config", help="Path to OpenHydroNet YAML config.")
    openhydronet_prepare = openhydronet_subparsers.add_parser(
        "prepare-inputs", help="Prepare OpenHydroNet-ready input package."
    )
    openhydronet_prepare.add_argument("config", help="Path to OpenHydroNet YAML config.")

    project_parser = subparsers.add_parser("project", help="HydroLite project workflow commands.")
    project_subparsers = project_parser.add_subparsers(dest="project_command", required=True)
    project_create = project_subparsers.add_parser("create", help="Create a HydroLite project.")
    project_create.add_argument("project_dir")
    project_info_parser = project_subparsers.add_parser("info", help="Show project metadata.")
    project_info_parser.add_argument("project_dir")
    project_validate = project_subparsers.add_parser("validate", help="Validate a HydroLite project.")
    project_validate.add_argument("project_dir")
    project_run = project_subparsers.add_parser("run", help="Run a case inside a HydroLite project.")
    project_run.add_argument("project_dir")
    project_run.add_argument("case_name")
    project_batch = project_subparsers.add_parser("batch", help="Run all project cases.")
    project_batch.add_argument("project_dir")
    project_compare = project_subparsers.add_parser("compare", help="Compare project outputs.")
    project_compare.add_argument("project_dir")
    project_export = project_subparsers.add_parser("export", help="Export a project package zip.")
    project_export.add_argument("project_dir")

    wizard_parser = subparsers.add_parser("wizard", help="HydroLite project wizard commands.")
    wizard_subparsers = wizard_parser.add_subparsers(dest="wizard_command", required=True)
    wizard_validate = wizard_subparsers.add_parser("validate", help="Validate a wizard template.")
    wizard_validate.add_argument("template")
    wizard_preview = wizard_subparsers.add_parser("preview", help="Preview a wizard template without creating files.")
    wizard_preview.add_argument("template")
    wizard_create = wizard_subparsers.add_parser("create", help="Create a project from a wizard template.")
    wizard_create.add_argument("template")
    wizard_create.add_argument("project_dir")
    wizard_create.add_argument("--force", action="store_true", help="Allow writing into an existing project directory.")

    report_parser = subparsers.add_parser("report", help="Project report export commands.")
    report_subparsers = report_parser.add_subparsers(dest="report_command", required=True)
    for command, help_text in (
        ("project", "Generate Markdown, Word, HTML, PDF/fallback, and report bundle."),
        ("markdown", "Generate project_report.md."),
        ("docx", "Generate project_report.docx."),
        ("html", "Generate project_report.html."),
        ("pdf", "Generate project_report.pdf or a PDF unavailable note."),
        ("bundle", "Generate project_report_bundle.zip."),
    ):
        report_command = report_subparsers.add_parser(command, help=help_text)
        report_command.add_argument("project_dir")

    tutorial_parser = subparsers.add_parser("tutorial", help="Guided demo tutorial commands.")
    tutorial_subparsers = tutorial_parser.add_subparsers(dest="tutorial_command", required=True)
    tutorial_subparsers.add_parser("list", help="List guided demo steps.")
    tutorial_checklist = tutorial_subparsers.add_parser("checklist", help="Check guided demo success files.")
    tutorial_checklist.add_argument("project_dir")
    tutorial_summary = tutorial_subparsers.add_parser("summary", help="Generate guided demo summary markdown.")
    tutorial_summary.add_argument("project_dir")
    tutorial_reset = tutorial_subparsers.add_parser("reset", help="Reset guided demo progress only.")
    tutorial_reset.add_argument("project_dir")

    templates_parser = subparsers.add_parser("templates", help="Real project data template commands.")
    templates_subparsers = templates_parser.add_subparsers(dest="templates_command", required=True)
    templates_subparsers.add_parser("list", help="List available data templates.")
    templates_export = templates_subparsers.add_parser("export", help="Export a single data template.")
    templates_export.add_argument("template_name")
    templates_export.add_argument("output_dir")
    templates_export_all = templates_subparsers.add_parser("export-all", help="Export all standard and example data templates.")
    templates_export_all.add_argument("output_dir")
    templates_validate = templates_subparsers.add_parser("validate", help="Validate a project input dataset directory.")
    templates_validate.add_argument("dataset_dir")
    templates_summary = templates_subparsers.add_parser("summary", help="Write a data template summary workbook and report.")
    templates_summary.add_argument("output_dir")

    beta_parser = subparsers.add_parser("beta", help="Beta release verification and feedback commands.")
    beta_subparsers = beta_parser.add_subparsers(dest="beta_command", required=True)
    beta_subparsers.add_parser("info", help="Show beta release links and docs.")
    beta_subparsers.add_parser("checklist", help="Show post-release beta verification checklist.")
    beta_subparsers.add_parser("smoke-local", help="Run lightweight local beta smoke checks.")

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
    if args.command == "version":
        print(f"app_name: {__app_name__}")
        print(f"version: {__version__}")
        print(f"release_date: {__release_date__}")
        print(f"python_version: {sys.version.split()[0]}")
        print(f"project_root: {Path(__file__).resolve().parents[1]}")
        return 0
    if args.command == "healthcheck":
        outputs = build_healthcheck()
        status = healthcheck_status(outputs)
        print(f"HydroLite healthcheck status: {status}")
        print(f"Report written to: {outputs.report_md}")
        print(f"Summary written to: {outputs.summary_xlsx}")
        return 0
    if args.command == "roadmap":
        root = Path(__file__).resolve().parents[1]
        print(f"current_stable_version: {__version__}")
        print("v0.7.0_goal: GIS/QGIS bridge, real project import, lightweight calibration, report templates, and desktop launcher planning.")
        print(f"roadmap: {root / 'docs' / 'roadmap_v0.7.0.md'}")
        print(f"milestones: {root / 'docs' / 'milestones_v0.7.0.md'}")
        print(f"issue_backlog: {root / 'docs' / 'issue_backlog_v0.7.0.md'}")
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
    if args.command == "qgis":
        if args.qgis_command == "paths":
            for item in detect_qgis_process_candidates():
                print(f"{item['path']} exists={item['exists']} executable={item['executable']}")
            return 0
        if args.qgis_command == "version":
            result = qgis_process_version()
            print(result.get("stdout") or result.get("stderr") or "WARNING qgis_process not available")
            return 0
        if args.qgis_command == "algorithms":
            result = qgis_process_algorithms(args.filter)
            algorithms = result.get("algorithms", [])
            if not algorithms:
                print(result.get("stderr") or "WARNING no algorithms returned")
                return 0
            for line in algorithms[:200]:
                print(line)
            if len(algorithms) > 200:
                print(f"... truncated {len(algorithms) - 200} more lines")
            return 0
        if args.qgis_command == "layer-info":
            import json

            print(json.dumps(qgis_layer_info(args.input_path), indent=2, ensure_ascii=False))
            return 0
        if args.qgis_command == "validate-layer":
            import json

            print(json.dumps(qgis_validate_vector_layer(args.input_path), indent=2, ensure_ascii=False))
            return 0
        if args.qgis_command == "export-vector":
            import json

            print(json.dumps(qgis_export_vector(args.input_path, args.output_path), indent=2, ensure_ascii=False))
            return 0
        if args.qgis_command == "export-csv":
            import json

            print(json.dumps(qgis_export_attributes_csv(args.input_path, args.output_csv), indent=2, ensure_ascii=False))
            return 0
        if args.qgis_command == "demo":
            summary = qgis_bridge_demo()
            print(f"QGIS bridge demo written to: {summary['outputs']['report']}")
            print(f"Summary written to: {summary['outputs']['summary']}")
            return 0
        if args.qgis_command == "infer-mapping":
            import json

            print(json.dumps(infer_hydrolite_field_mapping(args.layer_path, args.target_template), indent=2, ensure_ascii=False))
            return 0
        if args.qgis_command == "convert-subbasins":
            import json

            print(json.dumps(convert_geojson_to_subbasins_csv(args.layer_path, args.output_csv), indent=2, ensure_ascii=False))
            return 0
        if args.qgis_command == "convert-reaches":
            import json

            print(json.dumps(convert_geojson_to_reaches_csv(args.layer_path, args.output_csv), indent=2, ensure_ascii=False))
            return 0
        if args.qgis_command == "export-basin":
            import json

            print(json.dumps(export_basin_boundary_geojson(args.layer_path, args.output_geojson), indent=2, ensure_ascii=False))
            return 0
        if args.qgis_command == "to-hydrolite":
            import json

            print(
                json.dumps(
                    convert_qgis_layers_to_hydrolite_inputs(
                        args.subbasins_layer,
                        args.reaches_layer,
                        args.basin_layer,
                        args.output_dir,
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        if args.qgis_command == "validate-hydrolite":
            import json

            print(json.dumps(validate_qgis_to_hydrolite_outputs(args.output_dir), indent=2, ensure_ascii=False))
            return 0
        if args.qgis_command == "create-project":
            import json

            print(
                json.dumps(
                    create_project_from_qgis_outputs(
                        args.qgis_output_dir,
                        args.project_dir,
                        rainfall_csv=args.rainfall_csv,
                        project_name=args.project_name,
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        if args.qgis_command == "project-workflow":
            import json

            run_all = not (args.run_batch or args.run_compare or args.run_report)
            print(
                json.dumps(
                    run_qgis_project_workflow(
                        args.qgis_output_dir,
                        args.project_dir,
                        rainfall_csv=args.rainfall_csv,
                        run_batch=args.run_batch or run_all,
                        run_compare=args.run_compare or run_all,
                        run_report=args.run_report or run_all,
                    ),
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )
            return 0
        diagnosis = build_qgis_diagnosis()
        if args.qgis_command == "recommend":
            recommendation = recommend_qgis_bridge_mode(diagnosis)
            print(f"mode: {recommendation['mode']}")
            print(f"reason: {recommendation['reason']}")
            return 0
        if args.qgis_command == "diagnose":
            outputs = write_qgis_diagnosis()
            recommendation = diagnosis["recommendation"]
            print(f"QGIS diagnosis written to: {outputs['md']}")
            print(f"JSON written to: {outputs['json']}")
            print(f"recommended_mode: {recommendation['mode']}")
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
    if args.command == "project":
        if args.project_command == "create":
            summary = create_project(args.project_dir)
            print(f"HydroLite project created. Summary written to: {summary}")
            return 0
        if args.project_command == "info":
            import json

            print(json.dumps(project_info(args.project_dir), indent=2, ensure_ascii=False))
            return 0
        if args.project_command == "validate":
            result = validate_project(args.project_dir)
            print(f"Project validation written to: {result['xlsx']}")
            return 0
        if args.project_command == "run":
            outputs = run_project_case(args.project_dir, args.case_name)
            print(f"Project case complete. Outputs written to: {outputs.output_dir}")
            return 0
        if args.project_command == "batch":
            summary_path, rows, failed_cases = run_project_batch(args.project_dir)
            print(f"Project batch complete. Summary written to: {summary_path}")
            return 1 if failed_cases else 0
        if args.project_command == "compare":
            outputs = compare_project_outputs(args.project_dir)
            print(f"Project comparison written to: {outputs.output_dir}")
            return 0
        if args.project_command == "export":
            package = export_project_package(args.project_dir)
            print(f"Project package written to: {package}")
            return 0
    if args.command == "wizard":
        if args.wizard_command == "validate":
            result = validate_wizard_config(args.template)
            print(f"Wizard validation status: {result['status']}")
            for message in result["errors"]:
                print(f"ERROR {message}")
            for message in result["warnings"]:
                print(f"WARNING {message}")
            return 1 if result["errors"] else 0
        if args.wizard_command == "preview":
            import json

            print(json.dumps(preview_wizard(args.template), indent=2, ensure_ascii=False, default=str))
            return 0
        if args.wizard_command == "create":
            result = create_project_from_wizard(args.template, args.project_dir, force=args.force)
            print(f"Wizard project created: {result['project_dir']}")
            print(f"Project YAML: {result['project_yaml']}")
            print(f"Case file: {result['case_file']}")
            print(f"Wizard summary: {result['wizard_summary']}")
            print(f"Validation workbook: {result['validation_xlsx']}")
            return 0
    if args.command == "report":
        if args.report_command == "project":
            outputs = render_project_report_all(args.project_dir)
            print("Project report outputs:")
            for name, path in outputs.items():
                print(f"- {name}: {path}")
            return 0
        if args.report_command == "markdown":
            print(f"Project Markdown report written to: {render_project_report_markdown(args.project_dir)}")
            return 0
        if args.report_command == "docx":
            print(f"Project Word report written to: {render_project_report_docx(args.project_dir)}")
            return 0
        if args.report_command == "html":
            print(f"Project HTML report written to: {render_project_report_html(args.project_dir)}")
            return 0
        if args.report_command == "pdf":
            print(f"Project PDF report output written to: {render_project_report_pdf(args.project_dir)}")
            return 0
        if args.report_command == "bundle":
            print(f"Project report bundle written to: {export_project_report_bundle(args.project_dir)}")
            return 0
    if args.command == "tutorial":
        if args.tutorial_command == "list":
            for step in get_demo_steps():
                print(f"{step['step_id']}: {step['title']} [{step['page_name']}]")
                print(f"  CLI: {step['cli_equivalent']}")
            return 0
        if args.tutorial_command == "checklist":
            rows = get_demo_checklist(args.project_dir)
            for row in rows:
                print(
                    f"{row['step_id']}: {row['status']} "
                    f"files={row['success_file_count']}/{row['expected_file_count']} "
                    f"marked_complete={row['marked_complete']}"
                )
            return 0
        if args.tutorial_command == "summary":
            print(f"Demo summary written to: {generate_demo_summary(args.project_dir)}")
            return 0
        if args.tutorial_command == "reset":
            print(f"Demo progress reset: {reset_demo_progress(args.project_dir)}")
            return 0
    if args.command == "templates":
        if args.templates_command == "list":
            for row in list_data_templates():
                print(f"{row['template_name']}: {row['template_path']}")
                print(f"  fields: {', '.join(row['required_fields']) or 'GeoJSON Polygon/MultiPolygon'}")
            return 0
        if args.templates_command == "export":
            print(f"Data template exported to: {export_data_template(args.template_name, args.output_dir)}")
            return 0
        if args.templates_command == "export-all":
            paths = export_all_data_templates(args.output_dir)
            print(f"Exported {len(paths)} data template files to: {Path(args.output_dir).resolve()}")
            return 0
        if args.templates_command == "validate":
            result = validate_project_input_dataset(args.dataset_dir)
            print(f"Data template validation status: {result['status']}")
            for check in result["checks"]:
                print(
                    f"- {check['template_name']}: {check['status']} "
                    f"rows={check['rows']} errors={len(check['errors'])} warnings={len(check['warnings'])}"
                )
            return 1 if result["status"] == "failed" else 0
        if args.templates_command == "summary":
            outputs = write_data_template_summary(args.output_dir)
            print(f"Data template summary written to: {outputs['md']}")
            print(f"Data template workbook written to: {outputs['xlsx']}")
            return 0
    if args.command == "beta":
        if args.beta_command == "info":
            info = beta_info()
            print(f"version: {info['version']}")
            print(f"github_url: {info['github_url']}")
            print(f"streamlit_url: {info['streamlit_url']}")
            print(f"release_tag: {info['release_tag']}")
            print("docs:")
            for name, path in info["docs"].items():
                print(f"- {name}: {path}")
            return 0
        if args.beta_command == "checklist":
            for item in beta_checklist():
                print(f"- [{item['area']}] {item['check']}")
            return 0
        if args.beta_command == "smoke-local":
            result = beta_smoke_local()
            print(f"version: {result['version']}")
            print(f"healthcheck_status: {result['healthcheck_status']}")
            print(f"healthcheck_report: {result['healthcheck_report']}")
            print(f"readme_exists: {result['readme_exists']}")
            print(f"release_dir_exists: {result['release_dir_exists']}")
            print(f"streamlit_app_exists: {result['streamlit_app_exists']}")
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
