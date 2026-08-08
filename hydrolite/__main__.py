from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]

from hydrolite.__version__ import __app_name__, __release_date__, __version__
from hydrolite.batch import run_batch
from hydrolite.calibration import (
    DEFAULT_OUTPUT as CALIBRATION_OUTPUT,
    build_parameter_bounds,
    compare_best_case,
    create_calibrated_case,
    export_calibration_bundle,
    run_calibrated_case,
    run_oat_sensitivity,
    run_parameter_search,
    select_best_calibration_candidate,
    select_calibration_target,
    validate_calibrated_case,
    write_calibration_report,
    write_parameter_outputs,
    write_target_outputs,
)
from hydrolite.icesat2 import DEFAULT_OUTPUT as ICESAT2_OUTPUT, detect_earthdata_access, detect_icesat2_dependencies, identify_icesat2_product, run_icesat2_demo, select_icesat2_product_for_waterbody, build_icesat2_depth_profiles, build_stage_area_volume_curve, validate_icesat2_outputs
from hydrolite.rusle import detect_rusle_backends, run_rusle, validate_rusle_outputs
from hydrolite.conservation import load_conservation_scenario, run_hydrolite_conservation_scenario, write_conservation_report, run_conservation_audit, run_conservation_audit_v2
from hydrolite.water_balance_audit import reconcile_hydrologic_water_balance, write_water_balance_audit
from hydrolite.watershed_accounting import build_watershed_accounting, export_watershed_accounting_bundle, validate_watershed_accounting, write_watershed_accounting_report
from hydrolite.reservoir_routing import reservoir_diagnosis, run_reservoir_demo, load_reservoir_config, load_stage_area_volume_curve, load_stage_discharge_curve, validate_stage_area_volume_curve, validate_stage_discharge_curve, route_reservoir_level_pool, write_reservoir_routing_outputs, build_hms_reservoir_project, run_hms_reservoir_open_probe, run_hms_reservoir_compute_probe, extract_hms_reservoir_results, write_reservoir_comparison_report, validate_reservoir_routing, convert_stage_discharge_to_storage_discharge, validate_unique_storage_discharge, enforce_monotonic_storage_discharge, export_hms_413_storage_discharge_curve, build_hms_413_reservoir_project, evaluate_hms_413_reservoir_compute_gate
from hydrolite.hec_hms import discover_hms_reservoir_reference_projects, select_hms_413_outflow_curve_reference, copy_hms_reservoir_reference_to_output, run_hms_reservoir_reference_open, run_hms_reservoir_reference_compute, inspect_hms_reservoir_basin_blocks, inspect_hms_reservoir_paired_data, write_hms_reservoir_reference_report
from hydrolite.sediment_delivery import run_sediment_demo, _run as run_sediment_delivery, validate_sediment_outputs
from hydrolite.beta import beta_checklist, beta_info, beta_smoke_local
from hydrolite.compare import run_compare
from hydrolite.capability_registry import list_capabilities, write_capability_registry
from hydrolite.flood_forecast import (
    DEFAULT_OUTPUT as FORECAST_OUTPUT,
    assess_flood_forecast_readiness,
    create_flood_forecast_config,
    export_flood_forecast_bundle,
    run_flood_forecast_demo,
    run_flood_forecast_project,
    validate_flood_forecast_bundle,
    validate_flood_forecast_outputs,
)
from hydrolite.forecast_rainfall import load_forecast_rainfall, write_rainfall_ensemble
from hydrolite.forecast_uncertainty import (
    calculate_exceedance_probability,
    load_user_flood_thresholds,
)
from hydrolite.lstm_forecast import detect_torch_environment, run_lstm_synthetic_smoke_test
from hydrolite.ml_forecast import assess_ml_data_readiness, detect_ml_dependencies, run_ml_synthetic_demo
from hydrolite.model_registry import get_available_models, write_model_registry_report
from hydrolite.data_templates import (
    export_all_data_templates,
    export_data_template,
    list_data_templates,
    validate_project_input_dataset,
    write_data_template_summary,
)
from hydrolite.workspace import create_workspace, list_workspace_datasets
from hydrolite.data_registry import list_dataset_types, write_data_registry_report
from hydrolite.data_upload import (
    classify_uploaded_dataset,
    copy_upload_to_workspace,
    detect_file_format,
    inspect_uploaded_file,
    preview_uploaded_dataset,
)
from hydrolite.field_mapping import infer_field_mapping, save_field_mapping
from hydrolite.data_quality_center import run_workspace_quality_checks, write_data_quality_report
from hydrolite.data_lineage import validate_lineage_graph, write_lineage_report
from hydrolite.data_requirements import build_project_data_requirement_matrix, write_data_readiness_report
from hydrolite.connectors import get_connector, list_connectors
from hydrolite.data_acquisition import create_acquisition_plan, execute_acquisition_plan, write_acquisition_report
from hydrolite.input_builder import build_all_inputs
from hydrolite.data_center import write_data_center_reports
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
from hydrolite.hec_hms import (
    analyze_reference_precipitation,
    build_hec_hms_diagnosis,
    build_hms_run_command,
    copy_hms_reference_project_to_output,
    collect_hms_run_outputs,
    create_calibrated_hms_project_from_hydrolite,
    create_hms_project_from_hydrolite,
    detect_hms_cli_modes,
    detect_hec_hms_executables,
    detect_hec_hms_installations,
    discover_hms_reference_projects,
    hec_hms_version,
    parse_hms_logs,
    run_hms_compute_probe,
    run_hms_open_probe,
    run_hms_probe,
    run_hms_project,
    run_official_hms_reference,
    select_smallest_hms_reference_project,
    summarize_hms_run,
    validate_hms_project,
    validate_hms_run_outputs,
    write_hec_hms_diagnosis,
    write_hms_dss_discovery_report,
    write_hms_official_validation_summary,
    write_hms_run_scripts,
    write_hms_project_report,
)
from hydrolite.hec_hms_precipitation import (
    create_hms_rainfall_verified_project,
    evaluate_hms_rainfall_gate,
    map_project_rainfall,
    run_hms_rainfall_compute,
    run_hms_rainfall_open_probe,
    validate_project_rainfall_dss,
    write_dss_backend_diagnosis,
    write_hms_rainfall_gate_report,
    write_hms_result_catalog_report,
    write_normalized_rainfall_report,
    write_project_rainfall_dss,
    write_rainfall_validation_summary,
)
from hydrolite.hec_hms_format import compare_generated_to_reference, write_hms_format_comparison_report
from hydrolite.hec_hms_results import (
    DEFAULT_COMPARISON_DIR,
    DEFAULT_RESULTS_DIR,
    export_hms_comparison_bundle,
    load_hms_result_catalog,
    map_hms_results_to_hydrolite_elements,
    read_hms_dss_timeseries,
    run_hms_hydrolite_comparison,
    run_hms_result_extraction,
    select_verified_outlet_series,
    validate_hms_comparison_outputs,
    write_hms_comparison_report,
    write_hms_hydrolite_mapping_report,
    write_hms_timeseries_catalog,
    write_outlet_selection_report,
)
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
from hydrolite.watershed import (
    create_demo_dem,
    detect_watershed_backends,
    inspect_dem,
    run_watershed_mvp,
    validate_watershed_outputs,
    write_watershed_report,
)
from hydrolite.workflow_engine import (
    create_workflow_plan,
    list_workflow_stages,
    read_workflow_status,
    run_full_workflow,
    run_workflow_stage,
    summarize_workflow_outputs,
    validate_workflow_config,
)
from hydrolite.drought_cli import register_drought_cli, run_drought_cli
from hydrolite.research_registry import built_in_sources, write_research_outputs
from hydrolite.source_licensing import audit_source_licenses
from hydrolite.research_method_card import method_cards
from hydrolite.gee_catalog import (
    catalog_status, compare_datasets, generate_ee_code, get_catalog_dataset,
    recommend_datasets, refresh_catalog, search_catalog, validate_catalog,
    write_catalog_report,
)
from hydrolite.gee_catalog.reporting import build_catalog_statistics
from hydrolite.gee_catalog.loader import load_catalog_records
from hydrolite.gamma_lag_features import write_gamma_feature_report
from hydrolite.river_graph import write_graph_manifest
from hydrolite.graph_hydrology_features import build_node_feature_matrix, write_graph_feature_summary
from hydrolite.trend_aware_features import write_trend_feature_report
from hydrolite.hierarchical_multihorizon import write_multihorizon_report
from hydrolite.graph_temporal_residual import run_graph_temporal_residual
from hydrolite.water_quality_experiment import assess_water_quality_experiment, write_water_quality_method_demo
from hydrolite.method_benchmark import write_method_benchmark
from hydrolite.flood_susceptibility import readiness as susceptibility_readiness, train_adaptive as susceptibility_train_adaptive, train_baselines as susceptibility_train_baselines, validate_outputs as susceptibility_validate_outputs, write_report as susceptibility_write_report
from hydrolite.flood_susceptibility_features import build_conditioning_features
from hydrolite.flood_susceptibility_validation import spatial_block_cv


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

    calibration_parser = subparsers.add_parser("calibration", help="Bounded sensitivity and calibration/alignment commands.")
    calibration_subparsers = calibration_parser.add_subparsers(dest="calibration_command", required=True)
    for command in ("target", "sensitivity", "search"):
        child = calibration_subparsers.add_parser(command)
        child.add_argument("project_dir")
        child.add_argument("hms_comparison_dir")
        if command == "search": child.add_argument("--max-candidates", type=int, default=30)
    calibration_parameters = calibration_subparsers.add_parser("parameters")
    calibration_parameters.add_argument("project_dir")
    calibration_bounds = calibration_subparsers.add_parser("bounds")
    calibration_bounds.add_argument("project_dir")
    calibration_best = calibration_subparsers.add_parser("best")
    calibration_best.add_argument("search_dir")
    calibration_create = calibration_subparsers.add_parser("create-case")
    calibration_create.add_argument("project_dir"); calibration_create.add_argument("search_dir")
    calibration_run = calibration_subparsers.add_parser("run-best"); calibration_run.add_argument("project_dir")
    calibration_compare = calibration_subparsers.add_parser("compare-best"); calibration_compare.add_argument("project_dir"); calibration_compare.add_argument("hms_project_dir")
    calibration_report = calibration_subparsers.add_parser("report"); calibration_report.add_argument("output_dir")
    calibration_bundle = calibration_subparsers.add_parser("bundle"); calibration_bundle.add_argument("output_dir")
    calibration_validate = calibration_subparsers.add_parser("validate"); calibration_validate.add_argument("output_dir")

    icesat2_parser = subparsers.add_parser("icesat2")
    icesat2_sub = icesat2_parser.add_subparsers(dest="icesat2_command", required=True)
    icesat2_sub.add_parser("diagnose")
    x = icesat2_sub.add_parser("product-info"); x.add_argument("file")
    x = icesat2_sub.add_parser("select-product"); x.add_argument("waterbody_type"); x.add_argument("purpose")
    x = icesat2_sub.add_parser("search"); x.add_argument("bbox"); x.add_argument("start"); x.add_argument("end")
    x = icesat2_sub.add_parser("extract"); x.add_argument("file"); x.add_argument("waterbody_geojson"); x.add_argument("output_dir")
    x = icesat2_sub.add_parser("depth-profiles"); x.add_argument("output_dir")
    x = icesat2_sub.add_parser("storage-curve"); x.add_argument("output_dir")
    icesat2_sub.add_parser("demo"); x = icesat2_sub.add_parser("validate"); x.add_argument("output_dir")
    rusle_parser = subparsers.add_parser("rusle"); rusle_sub = rusle_parser.add_subparsers(dest="rusle_command", required=True)
    rusle_sub.add_parser("diagnose"); rusle_sub.add_parser("demo")
    x = rusle_sub.add_parser("run"); x.add_argument("config"); x.add_argument("output_dir")
    x = rusle_sub.add_parser("validate"); x.add_argument("output_dir")
    x = rusle_sub.add_parser("report"); x.add_argument("output_dir")
    conservation_parser = subparsers.add_parser("conservation"); conservation_sub = conservation_parser.add_subparsers(dest="conservation_command", required=True)
    x = conservation_sub.add_parser("run"); x.add_argument("project_dir"); x.add_argument("scenario_yaml")
    x = conservation_sub.add_parser("report"); x.add_argument("output_dir")
    x = conservation_sub.add_parser("validate"); x.add_argument("output_dir")
    x = conservation_sub.add_parser("audit"); x.add_argument("project_dir"); x.add_argument("scenario_dir")
    x = conservation_sub.add_parser("audit-v2"); x.add_argument("project_dir"); x.add_argument("scenario_dir")
    balance_parser = subparsers.add_parser("balance"); balance_sub = balance_parser.add_subparsers(dest="balance_command",required=True)
    x=balance_sub.add_parser("audit");x.add_argument("project_dir")
    x=balance_sub.add_parser("case");x.add_argument("project_dir");x.add_argument("case_name")
    x=balance_sub.add_parser("validate");x.add_argument("output_dir")
    x=balance_sub.add_parser("report");x.add_argument("output_dir")
    reservoir_parser = subparsers.add_parser("reservoir"); reservoir_sub = reservoir_parser.add_subparsers(dest="reservoir_command", required=True)
    reservoir_sub.add_parser("diagnose"); reservoir_sub.add_parser("demo")
    x=reservoir_sub.add_parser("validate-curves");x.add_argument("config")
    x=reservoir_sub.add_parser("route");x.add_argument("config");x.add_argument("output_dir")
    x=reservoir_sub.add_parser("hms-project");x.add_argument("config");x.add_argument("output_dir")
    x=reservoir_sub.add_parser("hms-open");x.add_argument("project_dir")
    x=reservoir_sub.add_parser("hms-compute");x.add_argument("project_dir")
    x=reservoir_sub.add_parser("compare");x.add_argument("reservoir_dir");x.add_argument("hms_project_dir")
    x=reservoir_sub.add_parser("validate");x.add_argument("output_dir")
    reservoir_sub.add_parser("reference-scan"); reservoir_sub.add_parser("reference-info"); reservoir_sub.add_parser("reference-open"); reservoir_sub.add_parser("reference-compute"); reservoir_sub.add_parser("compare-format")
    x=reservoir_sub.add_parser("convert-storage-discharge");x.add_argument("config")
    x=reservoir_sub.add_parser("hms413-project");x.add_argument("config");x.add_argument("output_dir")
    x=reservoir_sub.add_parser("hms413-open");x.add_argument("project_dir")
    x=reservoir_sub.add_parser("hms413-gate");x.add_argument("project_dir")
    x=reservoir_sub.add_parser("hms413-compute");x.add_argument("project_dir")
    x=reservoir_sub.add_parser("hms413-results");x.add_argument("project_dir")
    x=reservoir_sub.add_parser("compare-verified");x.add_argument("reservoir_dir");x.add_argument("hms_project_dir")
    x=reservoir_sub.add_parser("validate-verified");x.add_argument("project_dir")
    sediment_parser = subparsers.add_parser("sediment"); sediment_sub = sediment_parser.add_subparsers(dest="sediment_command", required=True)
    sediment_sub.add_parser("diagnose"); sediment_sub.add_parser("demo")
    x=sediment_sub.add_parser("deliver");x.add_argument("rusle_dir");x.add_argument("sdr_config");x.add_argument("output_dir")
    x=sediment_sub.add_parser("trap");x.add_argument("output_dir");x.add_argument("trapping_config")
    x=sediment_sub.add_parser("validate");x.add_argument("output_dir")
    x=sediment_sub.add_parser("report");x.add_argument("output_dir")
    accounting_parser = subparsers.add_parser("accounting"); accounting_sub = accounting_parser.add_subparsers(dest="accounting_command", required=True)
    x = accounting_sub.add_parser("build"); x.add_argument("project_dir")
    x = accounting_sub.add_parser("rebuild"); x.add_argument("project_dir")
    for command in ("completeness", "report", "bundle", "validate"):
        x = accounting_sub.add_parser(command); x.add_argument("output_dir")

    forecast_parser = subparsers.add_parser("forecast", help="Flood forecast and scenario ensemble MVP.")
    forecast_sub = forecast_parser.add_subparsers(dest="forecast_command", required=True)
    for command in ("diagnose", "models", "capabilities", "rainfall-demo", "physics-demo", "hydrolite-members", "hms-members", "reservoir-members", "ml-demo", "lstm-smoke", "hybrid-demo", "ensemble", "run-demo"):
        forecast_sub.add_parser(command)
    for command in ("readiness", "ml-readiness", "lstm-readiness"):
        x = forecast_sub.add_parser(command); x.add_argument("project_dir")
    x = forecast_sub.add_parser("create-config"); x.add_argument("project_dir"); x.add_argument("output_path")
    x = forecast_sub.add_parser("rainfall-ensemble"); x.add_argument("rainfall_file")
    x = forecast_sub.add_parser("thresholds"); x.add_argument("threshold_file")
    for command in ("report", "bundle", "validate"):
        x = forecast_sub.add_parser(command); x.add_argument("output_dir")
    x = forecast_sub.add_parser("run"); x.add_argument("project_dir"); x.add_argument("config_path"); x.add_argument("--output-dir", default=str(FORECAST_OUTPUT))

    data_parser = subparsers.add_parser("data", help="Unified data center and workspace commands.")
    data_sub = data_parser.add_subparsers(dest="data_command", required=True)
    for command in ("types", "formats", "templates"):
        data_sub.add_parser(command)
    for command in ("inspect", "preview", "classify"):
        x = data_sub.add_parser(command); x.add_argument("file")
    x = data_sub.add_parser("create-workspace"); x.add_argument("project_name"); x.add_argument("workspace_dir")
    x = data_sub.add_parser("upload"); x.add_argument("file"); x.add_argument("workspace_dir")
    x = data_sub.add_parser("mapping"); x.add_argument("dataset_id"); x.add_argument("workspace_dir")
    for command in ("quality", "lineage", "build-inputs"):
        x = data_sub.add_parser(command); x.add_argument("workspace_dir")
    x = data_sub.add_parser("requirements"); x.add_argument("workflow_id"); x.add_argument("workspace_dir")

    connectors_parser = subparsers.add_parser("connectors", help="External data connector status and acquisition plans.")
    connectors_sub = connectors_parser.add_subparsers(dest="connectors_command", required=True)
    for command in ("list", "status", "gee-status", "earthdata-status", "cds-status", "stac-status"):
        connectors_sub.add_parser(command)
    x = connectors_sub.add_parser("search"); x.add_argument("connector"); x.add_argument("dataset_type"); x.add_argument("config")
    x = connectors_sub.add_parser("plan"); x.add_argument("workspace_dir"); x.add_argument("workflow_id")
    x = connectors_sub.add_parser("execute-plan"); x.add_argument("plan"); x.add_argument("--dry-run", action="store_true"); x.add_argument("--execute", action="store_true")

    workflow_parser = subparsers.add_parser("workflow", help="v0.7.x full modeling workflow orchestration.")
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_command", required=True)
    workflow_subparsers.add_parser("list", help="List workflow stages and implementation status.")
    workflow_plan = workflow_subparsers.add_parser("plan", help="Create a dry-run workflow plan from a template.")
    workflow_plan.add_argument("config")
    workflow_plan.add_argument("output_dir")
    workflow_status = workflow_subparsers.add_parser("status", help="Show workflow status files for a project.")
    workflow_status.add_argument("project_dir")
    workflow_run_stage = workflow_subparsers.add_parser("run-stage", help="Dry-run one workflow stage for a project.")
    workflow_run_stage.add_argument("stage_id")
    workflow_run_stage.add_argument("project_dir")
    workflow_run_stage.add_argument("--config", default=None)
    workflow_run_stage.add_argument("--dry-run", action="store_true", help="Keep dry-run mode; this is the default.")
    workflow_run_stage.add_argument("--execute", action="store_true", help="Request non-dry-run mode for implemented stages.")
    workflow_run_full = workflow_subparsers.add_parser("run-full", help="Dry-run the full workflow for a project.")
    workflow_run_full.add_argument("project_dir")
    workflow_run_full.add_argument("--config", default=None)
    workflow_run_full.add_argument("--dry-run", action="store_true", help="Keep dry-run mode; this is the default.")
    workflow_run_full.add_argument("--execute", action="store_true", help="Request non-dry-run mode for implemented stages.")

    watershed_parser = subparsers.add_parser("watershed", help="Watershed diagnostics and small DEM processing MVP.")
    watershed_subparsers = watershed_parser.add_subparsers(dest="watershed_command", required=True)
    watershed_subparsers.add_parser("backends", help="Detect qgis_process watershed algorithm candidates.")
    watershed_demo = watershed_subparsers.add_parser("create-demo-dem", help="Create a small synthetic ASCII DEM.")
    watershed_demo.add_argument("output_path")
    watershed_inspect = watershed_subparsers.add_parser("inspect", help="Inspect a DEM with lightweight and QGIS checks.")
    watershed_inspect.add_argument("dem_path")
    watershed_subparsers.add_parser("mvp", help="Run the small watershed delineation MVP.")
    watershed_validate = watershed_subparsers.add_parser("validate", help="Validate watershed MVP outputs.")
    watershed_validate.add_argument("output_dir")
    watershed_report = watershed_subparsers.add_parser("report", help="Regenerate the watershed MVP report.")
    watershed_report.add_argument("output_dir")

    hms_parser = subparsers.add_parser("hms", help="HEC-HMS diagnostics and project generator MVP.")
    hms_subparsers = hms_parser.add_subparsers(dest="hms_command", required=True)
    hms_subparsers.add_parser("diagnose", help="Write HEC-HMS environment diagnosis outputs.")
    hms_subparsers.add_parser("paths", help="List HEC-HMS installation and executable candidates.")
    hms_subparsers.add_parser("version", help="Read HEC-HMS version safely when possible.")
    hms_create = hms_subparsers.add_parser("create-project", help="Generate an unverified HEC-HMS project skeleton.")
    hms_create.add_argument("project_dir")
    hms_create.add_argument("output_dir")
    hms_validate = hms_subparsers.add_parser("validate", help="Validate generated HEC-HMS project files.")
    hms_validate.add_argument("hms_project_dir")
    hms_report = hms_subparsers.add_parser("report", help="Regenerate the HEC-HMS project report.")
    hms_report.add_argument("hms_project_dir")
    hms_subparsers.add_parser("cli-modes", help="Detect safe HEC-HMS command-line modes and short script probe status.")
    hms_run_command = hms_subparsers.add_parser("run-command", help="Build a dry-run HEC-HMS command.")
    hms_run_command.add_argument("hms_project_dir")
    hms_write_scripts = hms_subparsers.add_parser("write-run-scripts", help="Write reusable HEC-HMS Jython, shell, and batch scripts.")
    hms_write_scripts.add_argument("hms_project_dir")
    hms_subparsers.add_parser("run-probe", help="Run a timeout-bounded HEC-HMS script-mode probe without simulation.")
    hms_run = hms_subparsers.add_parser("run", help="Dry-run by default; optionally execute the generated HEC-HMS command.")
    hms_run.add_argument("hms_project_dir")
    hms_run_mode = hms_run.add_mutually_exclusive_group()
    hms_run_mode.add_argument("--dry-run", action="store_true", help="Build reports without starting HEC-HMS; this is the default.")
    hms_run_mode.add_argument("--execute", action="store_true", help="Attempt HEC-HMS execution. MVP results require manual review.")
    hms_run.add_argument("--timeout", type=int, default=60, help="Execution timeout in seconds, capped at 60.")
    hms_collect = hms_subparsers.add_parser("collect-outputs", help="Collect HEC-HMS project, log, output, and DSS file metadata.")
    hms_collect.add_argument("hms_project_dir")
    hms_logs = hms_subparsers.add_parser("parse-logs", help="Parse HEC-HMS log keywords without reading DSS data.")
    hms_logs.add_argument("hms_project_dir")
    hms_summary = hms_subparsers.add_parser("run-summary", help="Write HEC-HMS run summary XLSX, Markdown, and JSON.")
    hms_summary.add_argument("hms_project_dir")
    hms_validate_run = hms_subparsers.add_parser("validate-run", help="Validate HEC-HMS run MVP outputs.")
    hms_validate_run.add_argument("hms_project_dir")
    hms_subparsers.add_parser("reference-scan", help="Scan bounded locations for official HEC-HMS reference projects.")
    hms_subparsers.add_parser("reference-info", help="Select and copy the smallest suitable official reference project.")
    hms_subparsers.add_parser("reference-open", help="Run an open-only probe on the copied official reference project.")
    hms_subparsers.add_parser("reference-compute", help="Compute the selected official reference run after the open gate passes.")
    hms_compare = hms_subparsers.add_parser("compare-format", help="Compare generated HEC-HMS component syntax with a reference project.")
    hms_compare.add_argument("reference_dir")
    hms_compare.add_argument("generated_dir")
    hms_calibrate = hms_subparsers.add_parser("calibrate-project", help="Generate a project calibrated to HEC-HMS 4.13 structure.")
    hms_calibrate.add_argument("project_dir")
    hms_calibrate.add_argument("output_dir")
    hms_open_probe = hms_subparsers.add_parser("open-probe", help="Run Project.open against a generated project.")
    hms_open_probe.add_argument("hms_project_dir")
    hms_compute_probe = hms_subparsers.add_parser("compute-probe", help="Attempt computeRun only when all safety gates pass.")
    hms_compute_probe.add_argument("hms_project_dir")
    hms_discover_dss = hms_subparsers.add_parser("discover-dss", help="List DSS file metadata without deep reading.")
    hms_discover_dss.add_argument("hms_project_dir")
    hms_subparsers.add_parser("official-validation-summary", help="Write the official/generated validation summary.")
    hms_subparsers.add_parser("precipitation-reference", help="Analyze official precipitation and DSS structures.")
    hms_subparsers.add_parser("dss-backends", help="Diagnose verified HEC-DSS write backends.")
    hms_normalize_rainfall = hms_subparsers.add_parser("normalize-rainfall", help="Normalize HydroLite rainfall for HEC-HMS.")
    hms_normalize_rainfall.add_argument("project_dir")
    hms_create_rainfall = hms_subparsers.add_parser("create-rainfall-project", help="Create a rainfall-mapped HEC-HMS project.")
    hms_create_rainfall.add_argument("project_dir")
    hms_create_rainfall.add_argument("output_dir")
    hms_write_rainfall = hms_subparsers.add_parser("write-rainfall-dss", help="Write and read back precipitation DSS data.")
    hms_write_rainfall.add_argument("project_dir")
    hms_write_rainfall.add_argument("hms_project_dir")
    for command, help_text in (
        ("validate-rainfall-dss", "Validate precipitation DSS read-back."),
        ("map-rainfall", "Generate and validate gage/met/control mapping."),
        ("rainfall-open-probe", "Open the rainfall-verified project."),
        ("rainfall-gate", "Evaluate the rainfall compute safety gate."),
        ("rainfall-compute", "Run gated HEC-HMS computeRun, capped at 120 seconds."),
        ("result-catalog", "Catalog and classify HEC-HMS result DSS pathnames."),
        ("rainfall-validation-summary", "Write the rainfall validation summary."),
    ):
        child = hms_subparsers.add_parser(command, help=help_text)
        child.add_argument("hms_project_dir")
    for command, help_text in (
        ("catalog-results", "Catalog and classify result DSS records."),
        ("list-flow-results", "List classified flow result pathnames."),
        ("read-flow-results", "Read all classified flow time series."),
        ("extract-results", "Run the complete HEC-HMS result extraction workflow."),
    ):
        child = hms_subparsers.add_parser(command, help=help_text)
        child.add_argument("hms_project_dir")
    for command, help_text in (
        ("map-results", "Map HEC-HMS flow results to HydroLite elements."),
        ("identify-outlet", "Identify topology-backed outlet candidates and series."),
        ("compare-hydrolite", "Compare the verified HMS outlet with HydroLite."),
    ):
        child = hms_subparsers.add_parser(command, help=help_text)
        child.add_argument("hms_project_dir")
        child.add_argument("hydrolite_project_dir")
    for command, help_text in (
        ("comparison-report", "Regenerate the HMS/HydroLite comparison report."),
        ("comparison-bundle", "Regenerate the safe HMS/HydroLite comparison bundle."),
        ("validate-comparison", "Validate HMS/HydroLite comparison outputs."),
    ):
        child = hms_subparsers.add_parser(command, help=help_text)
        child.add_argument("output_dir")

    runtime_parser = subparsers.add_parser("runtime", help="Production runtime operations.")
    runtime_sub = runtime_parser.add_subparsers(dest="runtime_command", required=True)
    for command in ("init", "status", "diagnose", "database", "processes", "recover"):
        runtime_sub.add_parser(command)
    runtime_cleanup = runtime_sub.add_parser("cleanup")
    runtime_cleanup_mode = runtime_cleanup.add_mutually_exclusive_group()
    runtime_cleanup_mode.add_argument("--dry-run", action="store_true")
    runtime_cleanup_mode.add_argument("--execute", action="store_true")

    projects_parser = subparsers.add_parser("projects", help="Registered project operations.")
    projects_sub = projects_parser.add_subparsers(dest="projects_command", required=True)
    for command in ("register", "import"):
        child = projects_sub.add_parser(command); child.add_argument("path")
    projects_sub.add_parser("list")
    for command in ("inspect", "readiness", "snapshot", "archive"):
        child = projects_sub.add_parser(command); child.add_argument("project_id")

    runs_parser = subparsers.add_parser("runs", help="Run planning and execution.")
    runs_sub = runs_parser.add_subparsers(dest="runs_command", required=True)
    for command in ("plan", "create"):
        child = runs_sub.add_parser(command); child.add_argument("project_id"); child.add_argument("workflow_id")
    runs_sub.add_parser("list")
    for command in ("start", "inspect", "progress", "cancel", "retry", "validate", "report"):
        child = runs_sub.add_parser(command); child.add_argument("run_id")
    retry_stage = runs_sub.add_parser("retry-stage"); retry_stage.add_argument("run_id"); retry_stage.add_argument("stage_id")

    tasks_parser = subparsers.add_parser("tasks", help="Local task queue operations.")
    tasks_sub = tasks_parser.add_subparsers(dest="tasks_command", required=True)
    for command in ("list", "queue", "run-once", "run-until-empty"):
        tasks_sub.add_parser(command)
    for command in ("inspect", "cancel", "retry", "logs"):
        child = tasks_sub.add_parser(command); child.add_argument("task_id")

    artifacts_parser = subparsers.add_parser("artifacts", help="Run artifact operations.")
    artifacts_sub = artifacts_parser.add_subparsers(dest="artifacts_command", required=True)
    artifacts_sub.add_parser("list")
    for command in ("run", "validate", "bundle"):
        child = artifacts_sub.add_parser(command); child.add_argument("run_id")
    inspect_artifact = artifacts_sub.add_parser("inspect"); inspect_artifact.add_argument("artifact_id")
    verify_bundle = artifacts_sub.add_parser("verify-bundle"); verify_bundle.add_argument("bundle")

    environment_parser = subparsers.add_parser("environment", help="Capture or compare environments.")
    environment_sub = environment_parser.add_subparsers(dest="environment_command", required=True)
    environment_sub.add_parser("capture")
    environment_compare = environment_sub.add_parser("compare"); environment_compare.add_argument("left"); environment_compare.add_argument("right")

    settings_parser = subparsers.add_parser("app-settings", help="Show and validate safe local settings.")
    settings_sub = settings_parser.add_subparsers(dest="settings_command", required=True)
    settings_sub.add_parser("show"); settings_sub.add_parser("validate")

    desktop_parser = subparsers.add_parser("desktop", help="Build and validate the macOS desktop distribution.")
    desktop_sub = desktop_parser.add_subparsers(dest="desktop_command", required=True)
    for command in (
        "diagnose", "build-env", "resources", "build-backend", "build-shell", "assemble",
        "build", "launch", "verify", "security-audit", "signing-status", "package-zip",
        "package-dmg", "notarization-gate", "staple", "update-status", "report", "validate",
    ):
        desktop_sub.add_parser(command)
    desktop_sign = desktop_sub.add_parser("sign")
    desktop_sign.add_argument("mode", nargs="?", default="ad_hoc", choices=["unsigned", "ad_hoc", "developer_id"])
    desktop_notarize = desktop_sub.add_parser("notarize")
    desktop_notarize.add_argument("mode", nargs="?", default="dry-run", choices=["dry-run", "execute"])
    desktop_appcast = desktop_sub.add_parser("appcast")
    desktop_appcast.add_argument("mode", nargs="?", default="dry-run", choices=["dry-run"])

    hindcast_parser = subparsers.add_parser("hindcast", help="Multi-event hindcast validation.")
    hindcast_sub = hindcast_parser.add_subparsers(dest="hindcast_command", required=True)
    for command in ("readiness", "detect-events", "event-catalog", "observation-qc", "map-stations", "build-events", "split-events"):
        child = hindcast_sub.add_parser(command)
        child.add_argument("workspace")
    for command in ("run-batch", "hms-batch", "calibrate-multi", "validate-parameters", "lead-time"):
        child = hindcast_sub.add_parser(command)
        child.add_argument("project")
    for command in ("run-event", "hms-event"):
        child = hindcast_sub.add_parser(command)
        child.add_argument("project")
        child.add_argument("event_id")
    for command in ("summarize", "parameter-stability", "report", "bundle", "validate"):
        child = hindcast_sub.add_parser(command)
        child.add_argument("output_dir")

    assimilation_parser = subparsers.add_parser("assimilation", help="Observed-flow data assimilation.")
    assimilation_sub = assimilation_parser.add_subparsers(dest="assimilation_command", required=True)
    assimilation_ready = assimilation_sub.add_parser("readiness")
    assimilation_ready.add_argument("workspace")
    assimilation_batch = assimilation_sub.add_parser("batch")
    assimilation_batch.add_argument("project")
    for command in ("nudging", "enkf", "compare"):
        child = assimilation_sub.add_parser(command)
        child.add_argument("project")
        child.add_argument("event_id")

    register_drought_cli(subparsers)
    water_quality = subparsers.add_parser("water-quality", help="Hydrology readiness gate for future water-quality work.")
    water_quality_sub = water_quality.add_subparsers(dest="water_quality_command", required=True)
    item = water_quality_sub.add_parser("hydrology-gate", help="Evaluate the continuous hydrology gate without running a water-quality model.")
    item.add_argument("output")

    research = subparsers.add_parser("research", help="Clean-room research source and method records.")
    research_sub = research.add_subparsers(dest="research_command", required=True)
    for command in ("sources", "registry", "licenses", "method-cards", "report"):
        research_sub.add_parser(command)

    gee_catalog = subparsers.add_parser("gee-catalog", help="Offline-first Google Earth Engine dataset metadata catalog.")
    gee_catalog_sub = gee_catalog.add_subparsers(dest="gee_catalog_command", required=True)
    gee_catalog_sub.add_parser("status")
    gee_catalog_sub.add_parser("stats")
    refresh = gee_catalog_sub.add_parser("refresh"); refresh.add_argument("mode", choices=["dry-run", "execute"])
    gee_catalog_sub.add_parser("validate")
    search = gee_catalog_sub.add_parser("search"); search.add_argument("query")
    dataset = gee_catalog_sub.add_parser("dataset"); dataset.add_argument("asset_id")
    compare_catalog = gee_catalog_sub.add_parser("compare"); compare_catalog.add_argument("asset_ids", nargs="+")
    recommend_catalog = gee_catalog_sub.add_parser("recommend"); recommend_catalog.add_argument("model_id"); recommend_catalog.add_argument("config", nargs="?", default=None)
    codegen_catalog = gee_catalog_sub.add_parser("codegen"); codegen_catalog.add_argument("asset_id"); codegen_catalog.add_argument("config", nargs="?", default=None); codegen_catalog.add_argument("--band", default=None); codegen_catalog.add_argument("--language", choices=["python", "javascript"], default="python")
    gee_catalog_sub.add_parser("report")

    method = subparsers.add_parser("method", help="Clean-room hydrologic and environmental method experiments.")
    method_sub = method.add_subparsers(dest="method_command", required=True)
    for command in ("gamma-demo", "graph-demo", "trend-demo", "multihorizon-demo", "graph-residual-demo", "water-quality-demo", "benchmark", "validate", "report"):
        method_sub.add_parser(command)

    susceptibility = subparsers.add_parser("susceptibility", help="Spatial flood-susceptibility method experiments.")
    susceptibility_sub = susceptibility.add_subparsers(dest="susceptibility_command", required=True)
    for command in ("readiness", "build-features", "split-spatial", "train-baselines", "train-adaptive"):
        child = susceptibility_sub.add_parser(command); child.add_argument("workspace")
    for command in ("explain", "validate", "report"):
        child = susceptibility_sub.add_parser(command); child.add_argument("output")
    return parser


def main(argv: list[str] | None = None) -> int:
    import json
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
        print("current_stable_version: 0.6.0-beta.1")
        print(f"current_development_version: {__version__}")
        print("v0.7.0_goal: GIS/QGIS bridge, real project import, lightweight calibration, report templates, and desktop launcher planning.")
        print(f"roadmap: {root / 'docs' / 'roadmap_v0.7.0.md'}")
        print(f"milestones: {root / 'docs' / 'milestones_v0.7.0.md'}")
        print(f"issue_backlog: {root / 'docs' / 'issue_backlog_v0.7.0.md'}")
        return 0
    if args.command in {"continuous", "drought"}:
        return run_drought_cli(args)
    if args.command == "research":
        output = ROOT / "output" / "research_methods"
        if args.research_command == "sources": result = {"sources": built_in_sources()}
        elif args.research_command == "licenses": result = {"licenses": audit_source_licenses()}
        elif args.research_command == "method-cards": result = {"method_cards": method_cards()}
        else:
            paths = write_research_outputs(output); result = {"status": "passed", "outputs": {key: str(value) for key, value in paths.items()}}
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0
    if args.command == "gee-catalog":
        output = ROOT / "output" / "gee_catalog_intelligence"; output.mkdir(parents=True, exist_ok=True)
        if args.gee_catalog_command == "status": result = catalog_status()
        elif args.gee_catalog_command == "refresh": result = refresh_catalog(args.mode)
        elif args.gee_catalog_command == "validate": result = validate_catalog()
        elif args.gee_catalog_command == "stats": result = build_catalog_statistics(load_catalog_records())
        elif args.gee_catalog_command == "search": result = search_catalog(args.query)
        elif args.gee_catalog_command == "dataset": result = {"status": "passed", "record": get_catalog_dataset(args.asset_id)} if get_catalog_dataset(args.asset_id) else {"status": "not_found", "asset_id": args.asset_id}
        elif args.gee_catalog_command == "compare": result = compare_datasets(args.asset_ids)
        elif args.gee_catalog_command == "recommend": result = recommend_datasets(args.model_id, args.config)
        elif args.gee_catalog_command == "codegen": result = generate_ee_code(args.asset_id, args.config, args.band, args.language)
        else:
            result = {"status": "passed", "outputs": {key: str(value) for key, value in write_catalog_report(output).items()}}
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0
    if args.command == "method":
        output = ROOT / "output" / "method_inspiration"; output.mkdir(parents=True, exist_ok=True)
        if args.method_command == "gamma-demo": result = write_gamma_feature_report(output)
        elif args.method_command == "graph-demo":
            graph = {"nodes": [f"S{i}" for i in range(1, 9)], "edges": [(f"S{i}", f"S{i+1}") for i in range(1, 8)]}; result = write_graph_manifest(graph, output); rows = [{"timestamp": "2020-01-01", "node_id": node, "precipitation": float(index), "pet": 2.0, "soil_moisture": .4, "surface_runoff": .1, "interflow": .05, "baseflow": .02, "total_water_yield": .17, "reach_flow": .17, "reservoir_storage": 0.0, "aet": 1.0} for index, node in enumerate(graph["nodes"], 1)]; result["features"] = str(write_graph_feature_summary(build_node_feature_matrix(rows), output))
        elif args.method_command == "trend-demo": result = write_trend_feature_report(output)
        elif args.method_command == "multihorizon-demo": result = write_multihorizon_report(output)
        elif args.method_command == "graph-residual-demo": result = run_graph_temporal_residual([1, 2, 3, 2], [1.1, 1.8, 3.2, 2.1])
        elif args.method_command == "water-quality-demo": result = {**assess_water_quality_experiment(), **write_water_quality_method_demo(output)}
        elif args.method_command == "benchmark": result = write_method_benchmark(output)
        elif args.method_command == "validate": result = {"status": "passed", "water_quality": "planned", "bidirectional_forecast": run_graph_temporal_residual([1, 2], [1, 2], mode="graph_bidirectional_hindcast_only", purpose="forecast")}
        else:
            paths = {"gamma": write_gamma_feature_report(output), "trend": write_trend_feature_report(output), "multihorizon": write_multihorizon_report(output), "benchmark": write_method_benchmark(output)}; (output / "method_inspiration_report.md").write_text("# Method inspiration experiments\n\nClean-room features and baselines only; no paper-model reproduction.\n", encoding="utf-8"); result = {"status": "passed", "outputs": {key: str(value) for key, value in paths.items()}}
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0
    if args.command == "susceptibility":
        output = ROOT / "output" / "flood_susceptibility"
        if args.susceptibility_command == "readiness": result = susceptibility_readiness(args.workspace)
        elif args.susceptibility_command == "build-features": result = build_conditioning_features(args.workspace)
        elif args.susceptibility_command == "split-spatial":
            from hydrolite.flood_susceptibility_features import build_synthetic_flood_features
            result = {"status": "passed", "folds": spatial_block_cv(build_synthetic_flood_features())}
        elif args.susceptibility_command == "train-baselines": result = susceptibility_train_baselines(args.workspace, output)
        elif args.susceptibility_command == "train-adaptive": result = susceptibility_train_adaptive(args.workspace, output)
        elif args.susceptibility_command == "explain": result = {"status": "passed" if (Path(args.output) / "feature_importance.xlsx").exists() else "missing_baseline", "fallback": "permutation_importance"}
        elif args.susceptibility_command == "validate": result = susceptibility_validate_outputs(args.output)
        else: result = susceptibility_write_report(args.output)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0 if result.get("status") not in {"failed", "missing_baseline"} else 1
    if args.command == "water-quality":
        from hydrolite.continuous_validation import evaluate_water_quality_hydrology_gate
        manifest = Path(args.output) / "summary" / "continuous_validation_manifest.json"
        if not manifest.exists():
            result = {"status": "blocked", "reason": "continuous validation manifest is missing"}
        else:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            result = payload.get("gate") or evaluate_water_quality_hydrology_gate(payload)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "desktop":
        from hydrolite.desktop.commands import run_desktop_command

        return run_desktop_command(args.desktop_command, getattr(args, "mode", None))
    if args.command == "runtime":
        from hydrolite.deployment import build_deployment_manifest, write_deployment_report
        from hydrolite.process_manager import cleanup_orphaned_runtime_processes, list_hydrolite_processes
        from hydrolite.runtime_db import get_database_version, initialize_runtime_database, list_project_records, list_run_records, list_task_records
        from hydrolite.runtime_paths import ensure_runtime_directories, get_runtime_db_path, get_runtime_root
        from hydrolite.runtime_recovery import recover_all_runtime
        if args.runtime_command == "init":
            ensure_runtime_directories(); path = initialize_runtime_database()
            print(json.dumps({"status": "passed", "database": str(path), "schema_version": get_database_version()}, indent=2)); return 0
        if args.runtime_command == "status":
            initialize_runtime_database()
            print(json.dumps({"status": "passed", "runtime_root": str(get_runtime_root()), "database": str(get_runtime_db_path()), "projects": len(list_project_records()), "runs": len(list_run_records()), "tasks": len(list_task_records())}, indent=2)); return 0
        if args.runtime_command == "diagnose":
            result = build_deployment_manifest(); paths = write_deployment_report(get_runtime_root() / "reports", result)
            print(json.dumps({"status": "passed", "outputs": {key: str(value) for key, value in paths.items()}}, indent=2)); return 0
        if args.runtime_command == "database":
            print(json.dumps({"status": "passed", "path": str(initialize_runtime_database()), "schema_version": get_database_version()}, indent=2)); return 0
        if args.runtime_command == "processes":
            print(json.dumps({"managed_processes": list_hydrolite_processes()}, indent=2)); return 0
        if args.runtime_command == "recover":
            print(json.dumps(recover_all_runtime(), indent=2, ensure_ascii=False)); return 0
        root = get_runtime_root()
        candidates = [path for name in ("temp", "cache") for path in root.glob(f"runs/*/{name}/*")]
        if args.execute:
            import shutil
            for path in candidates:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        print(json.dumps({"status": "executed" if args.execute else "dry_run", "candidates": [str(path) for path in candidates], "orphan_check": cleanup_orphaned_runtime_processes(root)}, indent=2)); return 0
    if args.command == "projects":
        from hydrolite.project_service import archive_project, import_existing_project, list_recent_projects, open_project, register_workspace_as_project, update_project_readiness, create_project_snapshot
        from hydrolite.runtime_paths import get_project_runtime_dir
        if args.projects_command == "register": result = register_workspace_as_project(args.path)
        elif args.projects_command == "import": result = import_existing_project(args.path)
        elif args.projects_command == "list": result = list_recent_projects()
        elif args.projects_command == "inspect": result = open_project(args.project_id)
        elif args.projects_command == "readiness": result = update_project_readiness(args.project_id)
        elif args.projects_command == "archive": result = archive_project(args.project_id)
        else:
            result = {"project_id": args.project_id, "snapshot": str(create_project_snapshot(args.project_id, get_project_runtime_dir(args.project_id) / "snapshots"))}
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0
    if args.command == "runs":
        from hydrolite.run_manager import calculate_run_progress, cancel_run, create_run, inspect_run, retry_failed_run, retry_from_stage, start_run, validate_run, write_run_reports
        from hydrolite.run_planner import build_run_plan
        from hydrolite.runtime_db import list_run_records
        if args.runs_command == "plan": result = build_run_plan(args.project_id, args.workflow_id)
        elif args.runs_command == "create": result = create_run(args.project_id, args.workflow_id)
        elif args.runs_command == "list": result = list_run_records()
        elif args.runs_command == "start": result = start_run(args.run_id)
        elif args.runs_command == "inspect": result = inspect_run(args.run_id)
        elif args.runs_command == "progress": result = calculate_run_progress(args.run_id)
        elif args.runs_command == "cancel": result = cancel_run(args.run_id)
        elif args.runs_command == "retry": result = retry_failed_run(args.run_id)
        elif args.runs_command == "retry-stage": result = retry_from_stage(args.run_id, args.stage_id)
        elif args.runs_command == "validate": result = validate_run(args.run_id)
        else: result = {key: str(value) for key, value in write_run_reports(args.run_id).items()}
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0 if not isinstance(result, dict) or result.get("status") != "failed" else 1
    if args.command == "tasks":
        from hydrolite.runtime_db import get_task_record, list_task_records
        from hydrolite.runtime_logging import read_task_log
        from hydrolite.task_engine import cancel_task, retry_task
        from hydrolite.task_queue import get_queue_status, run_queue_once, run_queue_until_empty
        if args.tasks_command == "list": result = list_task_records()
        elif args.tasks_command == "queue": result = get_queue_status()
        elif args.tasks_command == "run-once": result = run_queue_once()
        elif args.tasks_command == "run-until-empty": result = run_queue_until_empty()
        elif args.tasks_command == "inspect": result = get_task_record(args.task_id)
        elif args.tasks_command == "cancel": result = cancel_task(args.task_id)
        elif args.tasks_command == "retry": result = retry_task(args.task_id)
        else: result = read_task_log(args.task_id)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0
    if args.command == "artifacts":
        from hydrolite.artifact_store import create_artifact_bundle, discover_run_artifacts, preview_artifact, search_artifacts, verify_artifact_bundle
        from hydrolite.artifact_validation import validate_run_artifacts, write_artifact_validation_report
        from hydrolite.runtime_db import list_artifact_records
        from hydrolite.runtime_paths import get_run_dir
        if args.artifacts_command == "list": result = list_artifact_records()
        elif args.artifacts_command == "run": result = discover_run_artifacts(args.run_id)
        elif args.artifacts_command == "inspect":
            rows = [row for row in list_artifact_records() if row["artifact_id"] == args.artifact_id]
            result = {"artifact": rows[0], "preview": preview_artifact(rows[0]["path"])} if rows else {"status": "missing"}
        elif args.artifacts_command == "validate":
            result = validate_run_artifacts(args.run_id); result["outputs"] = {key: str(value) for key, value in write_artifact_validation_report(get_run_dir(args.run_id) / "reports", result).items()}
        elif args.artifacts_command == "bundle":
            path = create_artifact_bundle(args.run_id, get_run_dir(args.run_id) / "reports"); result = {"status": "passed", "bundle": str(path)}
        else: result = verify_artifact_bundle(args.bundle)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0 if not isinstance(result, dict) or result.get("status") != "failed" else 1
    if args.command == "environment":
        from hydrolite.environment_capture import capture_environment, compare_environment_snapshots, write_environment_snapshot
        from hydrolite.runtime_paths import get_runtime_root
        if args.environment_command == "capture":
            result = capture_environment(); result["outputs"] = {key: str(value) for key, value in write_environment_snapshot(get_runtime_root() / "environments" / result["environment_id"], result).items()}
        else: result = compare_environment_snapshots(args.left, args.right)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0
    if args.command == "app-settings":
        from hydrolite.app_settings import load_settings, validate_settings
        settings = load_settings()
        print(json.dumps(settings if args.settings_command == "show" else validate_settings(settings), indent=2, ensure_ascii=False)); return 0
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
    if args.command == "calibration":
        import json

        if args.calibration_command == "target":
            target = write_target_outputs(args.project_dir, args.hms_comparison_dir, CALIBRATION_OUTPUT)
            print(json.dumps(target, indent=2, ensure_ascii=False, default=str)); return 0 if target["target_mode"] != "unavailable" else 1
        if args.calibration_command in {"parameters", "bounds"}:
            parameters, bounds = write_parameter_outputs(args.project_dir, CALIBRATION_OUTPUT)
            frame = parameters if args.calibration_command == "parameters" else bounds
            print(frame.to_string(index=False)); return 0
        if args.calibration_command in {"sensitivity", "search"}:
            target = write_target_outputs(args.project_dir, args.hms_comparison_dir, CALIBRATION_OUTPUT)
            if target["target_mode"] == "unavailable":
                print("Calibration target unavailable."); return 1
            _, bounds = write_parameter_outputs(args.project_dir, CALIBRATION_OUTPUT)
            if args.calibration_command == "sensitivity":
                result = run_oat_sensitivity(args.project_dir, target, bounds, CALIBRATION_OUTPUT / "sensitivity")
                print(f"target_mode: {target['target_mode']}")
                print(f"candidates attempted: {len(result['results'])}; succeeded: {(result['results']['run_status'] == 'success').sum()}")
                print(f"report: {result['report']}")
            else:
                result = run_parameter_search(args.project_dir, target, bounds, CALIBRATION_OUTPUT / "search", args.max_candidates)
                print(f"target_mode: {target['target_mode']}")
                print(f"candidates attempted: {len(result['results'])}; succeeded: {len(result['ranked'])}")
                print(f"best candidate: {(result['best'] or {}).get('candidate_id', 'unavailable')}")
                print(f"report: {result['report']}")
            return 0
        if args.calibration_command == "best":
            candidates = pd.read_excel(Path(args.search_dir) / "calibration_candidates.xlsx")
            best = select_best_calibration_candidate(candidates)
            print(json.dumps(best or {}, indent=2, ensure_ascii=False, default=str)); return 0 if best else 1
        if args.calibration_command == "create-case":
            candidates = pd.read_excel(Path(args.search_dir) / "calibration_candidates.xlsx")
            best = select_best_calibration_candidate(candidates)
            output_case = Path(args.project_dir) / "cases" / "qgis_demo_aligned.yaml"
            result = create_calibrated_case(args.project_dir, best, output_case)
            print(json.dumps({key: str(value) for key, value in result.items()}, indent=2, ensure_ascii=False)); return 0
        if args.calibration_command == "run-best":
            case = Path(args.project_dir) / "cases" / "qgis_demo_aligned.yaml"
            validate_calibrated_case(case)
            outputs = run_calibrated_case(case)
            print(f"Best case complete: {outputs.output_dir}"); return 0
        if args.calibration_command == "compare-best":
            result = compare_best_case(args.project_dir, args.hms_project_dir)
            print(f"Best alignment report: {result['report']}"); return 0
        if args.calibration_command == "report":
            print(f"Calibration report: {write_calibration_report(args.output_dir)}"); return 0
        if args.calibration_command == "bundle":
            print(f"Calibration bundle: {export_calibration_bundle(args.output_dir)}"); return 0
        if args.calibration_command == "validate":
            output = Path(args.output_dir)
            required = [output / "calibration_target.json", output / "baseline_parameters.xlsx", output / "search" / "calibration_candidates.xlsx"]
            missing = [str(path) for path in required if not path.exists()]
            print(json.dumps({"status": "passed" if not missing else "failed", "missing": missing}, indent=2, ensure_ascii=False)); return 0 if not missing else 1
    if args.command == "icesat2":
        import json
        if args.icesat2_command == "diagnose": print(json.dumps({"dependencies": detect_icesat2_dependencies(), "earthdata": detect_earthdata_access()}, indent=2)); return 0
        if args.icesat2_command == "product-info": print(json.dumps(identify_icesat2_product(args.file), indent=2)); return 0
        if args.icesat2_command == "select-product": print(json.dumps(select_icesat2_product_for_waterbody(args.waterbody_type, args.purpose), indent=2)); return 0
        if args.icesat2_command == "demo": result=run_icesat2_demo(); print(f"ICESat-2 demo: {result['report']}"); return 0
        if args.icesat2_command == "depth-profiles": print(build_icesat2_depth_profiles(pd.read_csv(Path(args.output_dir)/"water_surface_points.csv")).to_string(index=False)); return 0
        if args.icesat2_command == "storage-curve": print(build_stage_area_volume_curve(ROOT/"data_demo/icesat2/demo_waterbody.geojson", None, depth_constraints=pd.read_csv(Path(args.output_dir)/"water_surface_points.csv")).to_string(index=False)); return 0
        if args.icesat2_command == "validate": result=validate_icesat2_outputs(args.output_dir); print(json.dumps(result,indent=2)); return 0 if result["status"]=="passed" else 1
        print(json.dumps({"status":"not_executed","message":"Online/HDF5 extraction is optional; no download."},indent=2)); return 0
    if args.command == "rusle":
        if args.rusle_command == "diagnose": print(detect_rusle_backends()); return 0
        if args.rusle_command == "demo": result=run_rusle(ROOT/"data_demo/rusle/demo_rusle_config.yaml", ROOT/"output/rusle"); print(result["output_dir"]); return 0
        if args.rusle_command == "run": result=run_rusle(args.config,args.output_dir); print(result["output_dir"]); return 0
        if args.rusle_command == "validate": result=validate_rusle_outputs(args.output_dir); print(result); return 0 if result["status"]=="passed" else 1
        if args.rusle_command == "report": print(Path(args.output_dir)/"rusle_report_zh.md"); return 0
    if args.command == "conservation":
        if args.conservation_command == "run": result=run_hydrolite_conservation_scenario(args.project_dir,load_conservation_scenario(args.scenario_yaml),ROOT/"output/conservation"); write_conservation_report(ROOT/"output/conservation",result); print(result["summary"].to_string(index=False)); return 0
        if args.conservation_command == "report": print(Path(args.output_dir)/"conservation_report.md"); return 0
        if args.conservation_command == "validate": print({"status":"passed" if (Path(args.output_dir)/"conservation_summary.xlsx").exists() else "failed"}); return 0
        if args.conservation_command == "audit": result=run_conservation_audit(args.project_dir,args.scenario_dir);print(result["status"]);return 0
        if args.conservation_command == "audit-v2": result=run_conservation_audit_v2(args.project_dir,args.scenario_dir);print(result["status"]);return 0
    if args.command == "balance":
        if args.balance_command in {"audit","case"}:
            result=reconcile_hydrologic_water_balance(args.project_dir,getattr(args,"case_name",None));paths=write_water_balance_audit(ROOT/"output/water_balance_audit",result);print(paths["report"]);return 0 if result["validation"]["status"]=="passed" else 1
        if args.balance_command == "validate":
            gate=json.loads((Path(args.output_dir)/"flood_forecast_gate.json").read_text());print(gate);return 0 if gate["status"]=="passed" else 1
        if args.balance_command == "report": print(Path(args.output_dir)/"water_balance_audit_report.md");return 0
    if args.command == "reservoir":
        if args.reservoir_command in {"reference-scan","reference-info","reference-open","reference-compute","compare-format"}:
            refs=discover_hms_reservoir_reference_projects();selected=select_hms_413_outflow_curve_reference(refs)
            if args.reservoir_command=="reference-scan": print(json.dumps(refs,indent=2,default=str));return 0
            if not selected: print("reference_unavailable");return 0
            root=ROOT/"output/hec_hms_reservoir_reference";copied=copy_hms_reservoir_reference_to_output(selected,root)
            if args.reservoir_command=="reference-info":
                info={"selected":selected,"basin":inspect_hms_reservoir_basin_blocks(copied),"paired":inspect_hms_reservoir_paired_data(copied)};write_hms_reservoir_reference_report(copied,info);print(json.dumps(info,indent=2,default=str));return 0
            if args.reservoir_command=="reference-open": print(json.dumps(run_hms_reservoir_reference_open(copied),indent=2,default=str));return 0
            if args.reservoir_command=="reference-compute": print(json.dumps(run_hms_reservoir_reference_compute(copied,timeout=120),indent=2,default=str));return 0
            print(json.dumps({"reference":selected,"generated":"not_built"},indent=2));return 0
        if args.reservoir_command == "diagnose": print(json.dumps(reservoir_diagnosis(),indent=2));return 0
        if args.reservoir_command == "demo": result=run_reservoir_demo();print(result["paths"]["report"]);return 0
        if args.reservoir_command == "validate-curves":
            cfg=load_reservoir_config(args.config);base=Path(args.config).expanduser().resolve().parent;checks={"stage_storage":validate_stage_area_volume_curve(load_stage_area_volume_curve(base/cfg["stage_area_volume_csv"])),"stage_discharge":validate_stage_discharge_curve(load_stage_discharge_curve(base/cfg["stage_discharge_csv"]))};print(json.dumps(checks,indent=2));return 0 if all(v["status"]=="passed" for v in checks.values()) else 1
        if args.reservoir_command == "route": result=run_reservoir_demo(args.config,args.output_dir);print(result["paths"]["summary"]);return 0
        if args.reservoir_command == "hms-project": print(build_hms_reservoir_project(args.config,args.output_dir)["report"]);return 0
        if args.reservoir_command == "hms-open": print(json.dumps(run_hms_reservoir_open_probe(args.project_dir),indent=2,default=str));return 0
        if args.reservoir_command == "hms-compute":
            result=run_hms_reservoir_compute_probe(args.project_dir);result["results"]=str(extract_hms_reservoir_results(args.project_dir)["path"]);print(json.dumps(result,indent=2));return 0
        if args.reservoir_command == "compare":
            h=pd.read_csv(Path(args.reservoir_dir)/"reservoir_routing_timeseries.csv");print(write_reservoir_comparison_report(ROOT/"output/reservoir_comparison",h)["report"]);return 0
        if args.reservoir_command == "validate":
            frame=pd.read_csv(Path(args.output_dir)/"reservoir_routing_timeseries.csv");result=validate_reservoir_routing(frame);print(result);return 0 if result["status"]=="passed" else 1
        if args.reservoir_command=="convert-storage-discharge":
            cfg=load_reservoir_config(args.config);base=Path(args.config).expanduser().resolve().parent;curve=convert_stage_discharge_to_storage_discharge(load_stage_area_volume_curve(base/cfg["stage_area_volume_csv"]),load_stage_discharge_curve(base/cfg["stage_discharge_csv"]));out=ROOT/"output/hec_hms_reservoir_verified/data/hydrolite_storage_discharge.csv";export_hms_413_storage_discharge_curve(curve,out);print({"path":str(out),"unique":validate_unique_storage_discharge(curve),"monotonic":enforce_monotonic_storage_discharge(curve)["status"]});return 0
        if args.reservoir_command=="hms413-project": print(build_hms_413_reservoir_project(args.config,args.output_dir)["project_dir"]);return 0
        if args.reservoir_command=="hms413-open": print(json.dumps(run_hms_reservoir_open_probe(args.project_dir),indent=2,default=str));return 0
        if args.reservoir_command=="hms413-gate": print(json.dumps(evaluate_hms_413_reservoir_compute_gate(args.project_dir),indent=2));return 0
        if args.reservoir_command=="hms413-compute": print(json.dumps({"status":"gate_failed","gate":evaluate_hms_413_reservoir_compute_gate(args.project_dir)},indent=2));return 0
        if args.reservoir_command=="hms413-results": print(json.dumps(extract_hms_reservoir_results(args.project_dir),indent=2,default=str));return 0
        if args.reservoir_command=="compare-verified": print(write_reservoir_comparison_report(ROOT/"output/reservoir_comparison_verified",pd.read_csv(Path(args.reservoir_dir)/"reservoir_routing_timeseries.csv"))["report"]);return 0
        if args.reservoir_command=="validate-verified": print(evaluate_hms_413_reservoir_compute_gate(args.project_dir));return 0
    if args.command == "sediment":
        if args.sediment_command == "diagnose": print({"status":"available","methods":["user_defined","area_empirical_demo"],"warning":"RUSLE is not outlet sediment."});return 0
        if args.sediment_command == "demo": print(run_sediment_demo()["output_dir"]);return 0
        if args.sediment_command == "deliver": print(run_sediment_delivery(args.rusle_dir,args.sdr_config,None,args.output_dir)["output_dir"]);return 0
        if args.sediment_command == "trap":
            root=Path(args.output_dir);print(run_sediment_delivery(ROOT/"output/rusle",ROOT/"data_demo/sediment/demo_sdr_config.yaml",args.trapping_config,root)["output_dir"]);return 0
        if args.sediment_command == "validate": result=validate_sediment_outputs(args.output_dir);print(result);return 0 if result["status"]=="passed" else 1
        if args.sediment_command == "report": print(Path(args.output_dir)/"sediment_delivery_report.md");return 0
    if args.command == "accounting":
        if args.accounting_command in {"build","rebuild"}: result=build_watershed_accounting(args.project_dir); print(result["accounting_status"]); return 0
        if args.accounting_command == "completeness": print(pd.read_excel(Path(args.output_dir)/"accounting_completeness_matrix.xlsx").to_string(index=False)); return 0
        if args.accounting_command == "report": print(write_watershed_accounting_report(args.output_dir,{})); return 0
        if args.accounting_command == "bundle": print(export_watershed_accounting_bundle(args.output_dir)); return 0
        if args.accounting_command == "validate": result=validate_watershed_accounting(args.output_dir); print(result); return 0 if result["status"]=="passed" else 1
    if args.command == "forecast":
        command = args.forecast_command
        if command == "diagnose":
            print(json.dumps({"status": "available_partial", "ml": detect_ml_dependencies(), "torch": detect_torch_environment(), "hec_hms_reservoir": "blocked_gate"}, indent=2, default=str)); return 0
        if command == "models":
            write_model_registry_report(FORECAST_OUTPUT); print(json.dumps(get_available_models({"project_dir": ROOT/"projects/qgis_workflow_project"}), indent=2, default=str)); return 0
        if command == "capabilities":
            write_capability_registry(FORECAST_OUTPUT); print(json.dumps(list_capabilities(), indent=2)); return 0
        if command == "readiness":
            result=assess_flood_forecast_readiness(args.project_dir); print(json.dumps(result,indent=2,default=str)); return 0 if result["status"]!="blocked_water_balance" else 1
        if command == "create-config": print(create_flood_forecast_config(args.project_dir,args.output_path)); return 0
        if command in {"rainfall-demo","rainfall-ensemble"}:
            source=ROOT/"data_demo/flood_forecast/demo_rainfall_forecast.csv" if command=="rainfall-demo" else args.rainfall_file
            rainfall=load_forecast_rainfall(source); paths=write_rainfall_ensemble(FORECAST_OUTPUT/"rainfall",rainfall);print(paths["summary"]);return 0
        if command == "ml-readiness": print(json.dumps(assess_ml_data_readiness(args.project_dir),indent=2));return 0
        if command == "lstm-readiness": print(json.dumps({"status":"insufficient_data","real_training_ready":False,**detect_torch_environment()},indent=2,default=str));return 0
        if command == "ml-demo": print(json.dumps(run_ml_synthetic_demo(ROOT/"data_demo/flood_forecast/demo_ml_timeseries.csv",FORECAST_OUTPUT/"ml"),indent=2,default=str));return 0
        if command == "lstm-smoke": print(json.dumps(run_lstm_synthetic_smoke_test(FORECAST_OUTPUT/"lstm"),indent=2,default=str));return 0
        if command in {"physics-demo","hydrolite-members","hms-members","reservoir-members","hybrid-demo","ensemble"}:
            if not (FORECAST_OUTPUT/"reports/flood_forecast_manifest.json").exists(): run_flood_forecast_demo()
            print(FORECAST_OUTPUT);return 0
        if command == "thresholds":
            ensemble=pd.read_csv(FORECAST_OUTPUT/"ensemble/ensemble_timeseries.csv");result=calculate_exceedance_probability(ensemble,load_user_flood_thresholds(args.threshold_file));result.to_excel(FORECAST_OUTPUT/"ensemble/threshold_exceedance.xlsx",index=False);print(result.to_string(index=False));return 0
        if command == "run-demo": result=run_flood_forecast_demo();print(json.dumps({"status":result["status"],"validation":result["validation"]},indent=2));return 0
        if command == "run": result=run_flood_forecast_project(args.project_dir,args.config_path,args.output_dir);print(json.dumps({"status":result["status"],"validation":result["validation"]},indent=2));return 0
        if command == "report": print(Path(args.output_dir)/"reports/flood_forecast_report_zh.md");return 0
        if command == "bundle": print(export_flood_forecast_bundle(args.output_dir));return 0 if validate_flood_forecast_bundle(args.output_dir)["status"]=="passed" else 1
        if command == "validate": result=validate_flood_forecast_outputs(args.output_dir);print(result);return 0 if result["status"]=="passed" else 1
    if args.command == "hindcast":
        from hydrolite.calibration import (
            calculate_parameter_stability,
            run_multi_event_parameter_search,
            validate_robust_parameter_set,
        )
        from hydrolite.event_dataset import build_event_dataset
        from hydrolite.event_split import split_events_chronologically
        from hydrolite.hec_hms_hindcast import run_hms_hindcast_batch, run_hms_hindcast_event, write_hms_hindcast_report
        from hydrolite.hindcast import (
            DEFAULT_OUTPUT as HINDCAST_OUTPUT,
            DEMO_SOURCE as HINDCAST_DEMO,
            _catalog as hindcast_catalog,
            export_hindcast_validation_bundle,
            prepare_hindcast_workspace,
            run_hydrolite_hindcast_batch,
            run_hydrolite_hindcast_event,
            summarize_hindcast_validation,
            validate_hindcast_outputs,
        )
        from hydrolite.lead_time_validation import run_lead_time_validation
        from hydrolite.validation_readiness import assess_hindcast_readiness, write_validation_readiness_report

        command = args.hindcast_command
        if command in {"readiness", "detect-events", "event-catalog", "observation-qc", "map-stations", "build-events", "split-events"}:
            readiness = assess_hindcast_readiness(args.workspace)
            if readiness["status"] == "missing_data":
                write_validation_readiness_report(HINDCAST_OUTPUT / "readiness", readiness)
                print(json.dumps(readiness, indent=2, default=str))
                return 0
            result = prepare_hindcast_workspace(args.workspace, HINDCAST_OUTPUT)
            if command == "readiness":
                write_validation_readiness_report(HINDCAST_OUTPUT / "readiness", readiness)
                print(json.dumps(readiness, indent=2, default=str))
            else:
                print(json.dumps({"status": "passed", "command": command, **result}, indent=2, default=str))
            return 0
        project = Path(getattr(args, "project", ROOT / "projects/qgis_workflow_project"))
        prepare_hindcast_workspace(HINDCAST_DEMO, HINDCAST_OUTPUT)
        catalog = hindcast_catalog(HINDCAST_DEMO, HINDCAST_OUTPUT)
        if command == "run-event":
            rows = catalog[catalog["event_id"].astype(str) == args.event_id]
            if rows.empty:
                print(f"Unknown event_id: {args.event_id}"); return 1
            event = build_event_dataset(rows.iloc[0].to_dict(), HINDCAST_DEMO)
            result = run_hydrolite_hindcast_event(project, event, None, HINDCAST_OUTPUT / "hydrolite" / args.event_id)
            print(json.dumps(result, indent=2, default=str)); return 0 if result["run_status"] == "success" else 1
        if command == "run-batch":
            result = run_hydrolite_hindcast_batch(project, catalog, output_dir=HINDCAST_OUTPUT / "hydrolite")
            print(json.dumps(result, indent=2, default=str)); return 0
        if command in {"hms-event", "hms-batch"}:
            if command == "hms-event":
                rows = catalog[catalog["event_id"].astype(str) == args.event_id]
                result = run_hms_hindcast_event(rows.iloc[0].to_dict(), project, timeout=120) if not rows.empty else {"status": "failed", "error_message": "unknown event"}
            else:
                result = run_hms_hindcast_batch(catalog, {"project_dir": project, "timeout": 120})
            write_hms_hindcast_report(HINDCAST_OUTPUT / "hec_hms", result)
            print(json.dumps(result, indent=2, default=str)); return 0
        split = split_events_chronologically(catalog)
        if command == "calibrate-multi":
            calibration_events = catalog[catalog["event_id"].isin(split["calibration"])]
            result = run_multi_event_parameter_search(project, calibration_events, {"max_candidates": 30, "output_dir": HINDCAST_OUTPUT / "calibration"})
            run_hydrolite_hindcast_batch(project, catalog, result["best"], HINDCAST_OUTPUT / "hydrolite")
            print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2, default=str)); return 0
        if command == "validate-parameters":
            parameter_file = HINDCAST_OUTPUT / "calibration" / "robust_parameters.yaml"
            parameters = yaml.safe_load(parameter_file.read_text(encoding="utf-8")) if parameter_file.exists() else {}
            events = catalog[catalog["event_id"].isin(split["validation"])]
            result = validate_robust_parameter_set(parameters, events, project)
            print(json.dumps(result, indent=2, default=str)); return 0
        if command == "parameter-stability":
            path = Path(args.output_dir) / "calibration" / "candidates.xlsx"
            result = calculate_parameter_stability(pd.read_excel(path)) if path.exists() else {"status": "missing_data"}
            print(json.dumps(result, indent=2, default=str)); return 0
        if command == "lead-time":
            from hydrolite.data_assimilation import run_assimilation_batch
            run_assimilation_batch(project, HINDCAST_OUTPUT / "assimilation")
            result = run_lead_time_validation(HINDCAST_OUTPUT / "assimilation", HINDCAST_OUTPUT / "lead_time", [1, 3, 6, 12])
            print(json.dumps({k: v for k, v in result.items() if not isinstance(v, pd.DataFrame)}, indent=2, default=str)); return 0
        result = summarize_hindcast_validation(args.output_dir)
        if command == "bundle":
            print(export_hindcast_validation_bundle(args.output_dir)); return 0
        if command == "validate":
            validation = validate_hindcast_outputs(args.output_dir); print(validation); return 0 if validation["status"] == "passed" else 1
        print(json.dumps(result, indent=2, default=str)); return 0
    if args.command == "assimilation":
        from hydrolite.data_assimilation import build_assimilation_config, run_assimilation_batch, run_event_data_assimilation
        from hydrolite.hindcast import DEFAULT_OUTPUT as HINDCAST_OUTPUT, DEMO_SOURCE as HINDCAST_DEMO, _catalog as hindcast_catalog, prepare_hindcast_workspace, run_hydrolite_hindcast_batch
        from hydrolite.validation_readiness import assess_assimilation_readiness
        if args.assimilation_command == "readiness":
            print(json.dumps(assess_assimilation_readiness(args.workspace), indent=2, default=str)); return 0
        project = Path(args.project)
        prepare_hindcast_workspace(HINDCAST_DEMO, HINDCAST_OUTPUT)
        if not list((HINDCAST_OUTPUT / "hydrolite").glob("*/aligned.csv")):
            run_hydrolite_hindcast_batch(project, hindcast_catalog(HINDCAST_DEMO, HINDCAST_OUTPUT))
        if args.assimilation_command == "batch":
            result = run_assimilation_batch(project, HINDCAST_OUTPUT / "assimilation")
            print(json.dumps({k: v for k, v in result.items() if not isinstance(v, pd.DataFrame)}, indent=2, default=str)); return 0
        aligned = HINDCAST_OUTPUT / "hydrolite" / args.event_id / "aligned.csv"
        if not aligned.exists():
            print(f"Missing event result: {aligned}"); return 1
        result = run_event_data_assimilation(aligned, build_assimilation_config(project), HINDCAST_OUTPUT / "assimilation" / args.event_id)
        metric = {"nudging": "nudging_metrics", "enkf": "enkf_metrics", "compare": "open_loop_metrics"}[args.assimilation_command]
        print(json.dumps({"status": result["status"], metric: result[metric]}, indent=2, default=str)); return 0
    if args.command == "data":
        output = ROOT / "output" / "data_center"
        output.mkdir(parents=True, exist_ok=True)
        if args.data_command == "types":
            paths = write_data_registry_report(output)
            rows = list_dataset_types()
            print(f"dataset_types: {len(rows)}")
            for row in rows:
                print(f"- {row['dataset_type_id']}: {row['domain']}")
            print(f"registry: {paths['registry']}")
            return 0
        if args.data_command == "formats":
            paths = write_data_registry_report(output)
            print("\n".join(sorted({fmt for row in list_dataset_types() for fmt in row["supported_formats"]})))
            print(f"supported_formats: {paths['formats']}")
            return 0
        if args.data_command == "templates":
            files = sorted(path for path in (ROOT / "templates" / "data_upload").glob("*") if path.is_file())
            for path in files:
                print(path.relative_to(ROOT))
            print(f"template_count: {len(files)}")
            return 0
        if args.data_command == "inspect":
            print(json.dumps(inspect_uploaded_file(args.file), indent=2, ensure_ascii=False, default=str)); return 0
        if args.data_command == "preview":
            print(json.dumps(preview_uploaded_dataset(args.file), indent=2, ensure_ascii=False, default=str)); return 0
        if args.data_command == "classify":
            print(json.dumps(classify_uploaded_dataset(args.file), indent=2, ensure_ascii=False)); return 0
        if args.data_command == "create-workspace":
            print(json.dumps(create_workspace(args.workspace_dir, args.project_name), indent=2, ensure_ascii=False)); return 0
        if args.data_command == "upload":
            print(json.dumps(copy_upload_to_workspace(args.file, args.workspace_dir), indent=2, ensure_ascii=False)); return 0
        if args.data_command == "mapping":
            root = Path(args.workspace_dir).resolve()
            record = next((row for row in list_workspace_datasets(root) if row["dataset_id"] == args.dataset_id), None)
            if not record:
                raise KeyError(f"Unknown dataset_id: {args.dataset_id}")
            path = root / record["raw_path"]
            if detect_file_format(path) not in {"csv", "tsv"}:
                print(json.dumps({"status": "needs_manual_mapping", "dataset_id": args.dataset_id}, indent=2)); return 0
            frame = pd.read_csv(path, sep="\t" if detect_file_format(path) == "tsv" else ",")
            dataset_type = record.get("user_declared_type") or record.get("classification", {}).get("dataset_type")
            result = infer_field_mapping(frame, dataset_type)
            save_field_mapping(result, root / "mappings" / f"{args.dataset_id}.json")
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0
        if args.data_command == "quality":
            result = run_workspace_quality_checks(args.workspace_dir)
            paths = write_data_quality_report(output, result)
            print(json.dumps({"status": result["status"], "dataset_count": result["dataset_count"], "outputs": {key: str(value) for key, value in paths.items()}}, indent=2, ensure_ascii=False)); return 0
        if args.data_command == "requirements":
            matrix = build_project_data_requirement_matrix(args.workflow_id, args.workspace_dir)
            paths = write_data_readiness_report(output, {"workflow_id": args.workflow_id, "matrix": matrix})
            print(json.dumps({"status": "completed", "rows": len(matrix), "outputs": {key: str(value) for key, value in paths.items()}}, indent=2, ensure_ascii=False)); return 0
        if args.data_command == "lineage":
            result = validate_lineage_graph(args.workspace_dir)
            paths = write_lineage_report(output, result)
            print(json.dumps({"status": result["status"], "record_count": result["record_count"], "outputs": {key: str(value) for key, value in paths.items()}}, indent=2)); return 0
        if args.data_command == "build-inputs":
            result = build_all_inputs(args.workspace_dir, output)
            result["data_center_reports"] = {key: str(value) for key, value in write_data_center_reports(output, args.workspace_dir).items()}
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str)); return 0
    if args.command == "connectors":
        output = ROOT / "output" / "data_center"
        output.mkdir(parents=True, exist_ok=True)
        if args.connectors_command in {"list", "status"}:
            rows = list_connectors()
            pd.DataFrame(rows).to_excel(output / "connector_status.xlsx", index=False)
            print(json.dumps(rows, indent=2, ensure_ascii=False, default=str)); return 0
        if args.connectors_command.endswith("-status"):
            connector_id = args.connectors_command.removesuffix("-status")
            print(json.dumps(get_connector(connector_id).healthcheck(), indent=2, ensure_ascii=False, default=str)); return 0
        if args.connectors_command == "search":
            config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
            config["dataset_type"] = args.dataset_type
            print(json.dumps(get_connector(args.connector).search(config), indent=2, ensure_ascii=False, default=str)); return 0
        if args.connectors_command == "plan":
            plan = create_acquisition_plan(args.workspace_dir, args.workflow_id)
            paths = write_acquisition_report(output, plan)
            print(json.dumps({"status": plan["status"], "steps": len(plan["steps"]), "outputs": {key: str(value) for key, value in paths.items()}}, indent=2)); return 0
        if args.connectors_command == "execute-plan":
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            print(json.dumps(execute_acquisition_plan(plan, execute=bool(args.execute)), indent=2, ensure_ascii=False, default=str)); return 0
    if args.command == "workflow":
        if args.workflow_command == "list":
            for stage in list_workflow_stages():
                print(f"{stage['stage_id']}: {stage['status']} - {stage['title_zh']} / {stage['title_en']}")
                print(f"  CLI: {stage['cli_command']}")
            return 0
        if args.workflow_command == "plan":
            validation = validate_workflow_config(args.config)
            plan = create_workflow_plan(args.config, args.output_dir)
            print(f"Workflow validation status: {validation['status']}")
            print(f"Workflow plan written to: {plan['plan_json']}")
            print(f"Workflow plan markdown: {plan['plan_md']}")
            return 1 if validation["errors"] else 0
        if args.workflow_command == "status":
            import json

            print(
                json.dumps(
                    {
                        "status": read_workflow_status(args.project_dir),
                        "outputs": summarize_workflow_outputs(args.project_dir),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        if args.workflow_command == "run-stage":
            import json

            result = run_workflow_stage(
                args.stage_id,
                args.project_dir,
                config_path=args.config,
                dry_run=not args.execute,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.workflow_command == "run-full":
            import json

            result = run_full_workflow(args.project_dir, config_path=args.config, dry_run=not args.execute)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
    if args.command == "watershed":
        import json

        if args.watershed_command == "backends":
            print(json.dumps(detect_watershed_backends(), indent=2, ensure_ascii=False))
            return 0
        if args.watershed_command == "create-demo-dem":
            print(f"Demo DEM written to: {create_demo_dem(args.output_path)}")
            return 0
        if args.watershed_command == "inspect":
            print(json.dumps(inspect_dem(args.dem_path), indent=2, ensure_ascii=False))
            return 0
        if args.watershed_command == "mvp":
            result = run_watershed_mvp()
            print(f"Watershed MVP status: {result['status']}")
            print(f"Outputs written to: {result['output_dir']}")
            return 0
        if args.watershed_command == "validate":
            result = validate_watershed_outputs(args.output_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["status"] == "failed" else 0
        if args.watershed_command == "report":
            output = Path(args.output_dir).expanduser().resolve()
            diagnosis = output / "watershed_diagnosis.json"
            if diagnosis.exists():
                result = json.loads(diagnosis.read_text(encoding="utf-8"))
            else:
                result = {"status": "unavailable", "output_dir": str(output), "outputs": {}, "steps": {}}
            print(f"Watershed report written to: {write_watershed_report(output, result)}")
            return 0
    if args.command == "hms":
        import json

        reference_root = Path("output/hec_hms_reference").resolve()
        reference_project = reference_root / "reference_project"

        def ensure_reference_project() -> tuple[Path | None, dict | None]:
            if list(reference_project.glob("*.hms")):
                return reference_project, None
            selected = select_smallest_hms_reference_project(discover_hms_reference_projects())
            if not selected:
                return None, None
            return copy_hms_reference_project_to_output(selected, reference_project), selected

        if args.hms_command == "paths":
            print(
                json.dumps(
                    {
                        "installations": detect_hec_hms_installations(),
                        "executables": detect_hec_hms_executables(),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        if args.hms_command == "diagnose":
            outputs = write_hec_hms_diagnosis()
            diagnosis = build_hec_hms_diagnosis()
            print(f"HEC-HMS diagnosis written to: {outputs['md']}")
            print(f"JSON written to: {outputs['json']}")
            print(f"recommended_integration: {diagnosis['recommended_integration']}")
            return 0
        if args.hms_command == "version":
            print(json.dumps(hec_hms_version(), indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "create-project":
            result = create_hms_project_from_hydrolite(args.project_dir, args.output_dir)
            print(f"HEC-HMS project status: {result['status']}")
            print(f"Runnable status: {result['runnable_status']}")
            print(f"Project written to: {result['hms_project_dir']}")
            return 0
        if args.hms_command == "validate":
            result = validate_hms_project(args.hms_project_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["status"] == "failed" else 0
        if args.hms_command == "report":
            root = Path(args.hms_project_dir).expanduser().resolve()
            manifest = root / "reports" / "hec_hms_project_manifest.json"
            result = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {
                "status": "project_generation_mvp",
                "runnable_status": "unverified",
                "hms_project_dir": str(root),
                "validation": validate_hms_project(root),
                "warnings": ["Manifest unavailable; report regenerated from file checks only."],
            }
            print(f"HEC-HMS project report written to: {write_hms_project_report(root, result)}")
            return 0
        if args.hms_command == "cli-modes":
            print(json.dumps(detect_hms_cli_modes(), indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "run-command":
            print(json.dumps(build_hms_run_command(args.hms_project_dir), indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "write-run-scripts":
            outputs = write_hms_run_scripts(args.hms_project_dir)
            print(json.dumps({name: str(path) for name, path in outputs.items()}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "run-probe":
            print(json.dumps(run_hms_probe(), indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "run":
            result = run_hms_project(args.hms_project_dir, timeout=args.timeout, execute=args.execute)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "collect-outputs":
            print(json.dumps(collect_hms_run_outputs(args.hms_project_dir), indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "parse-logs":
            print(json.dumps(parse_hms_logs(args.hms_project_dir), indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "run-summary":
            result = summarize_hms_run(args.hms_project_dir)
            print(f"HEC-HMS run summary written to: {result['summary_xlsx']}")
            print(f"Run report written to: {result['run_report']}")
            return 0
        if args.hms_command == "validate-run":
            result = validate_hms_run_outputs(args.hms_project_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["status"] == "failed" else 0
        if args.hms_command == "reference-scan":
            candidates = discover_hms_reference_projects()
            selected = select_smallest_hms_reference_project(candidates)
            reports = reference_root / "reports"
            reports.mkdir(parents=True, exist_ok=True)
            output = reports / "reference_candidates.json"
            output.write_text(
                json.dumps({"candidates": candidates, "selected": selected}, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(json.dumps({"candidate_count": len(candidates), "selected": selected, "report": str(output)}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "reference-info":
            selected = select_smallest_hms_reference_project(discover_hms_reference_projects())
            if not selected:
                print("HEC-HMS official reference status: reference_not_found")
                return 0
            copied = copy_hms_reference_project_to_output(selected, reference_project)
            print(json.dumps({"selected": selected, "copied_to": str(copied)}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command in {"reference-open", "reference-compute"}:
            copied, _ = ensure_reference_project()
            if copied is None:
                print("HEC-HMS official reference status: reference_not_found; probe skipped")
                return 0
            result = run_official_hms_reference(
                copied,
                execute=args.hms_command == "reference-compute",
                timeout=120,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0
        if args.hms_command == "compare-format":
            comparison = compare_generated_to_reference(args.reference_dir, args.generated_dir)
            outputs = write_hms_format_comparison_report(reference_root / "reports", comparison)
            print(json.dumps({"status": comparison["status"], "outputs": {key: str(value) for key, value in outputs.items()}}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "calibrate-project":
            result = create_calibrated_hms_project_from_hydrolite(args.project_dir, args.output_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0
        if args.hms_command == "open-probe":
            print(json.dumps(run_hms_open_probe(args.hms_project_dir), indent=2, ensure_ascii=False, default=str))
            return 0
        if args.hms_command == "compute-probe":
            print(json.dumps(run_hms_compute_probe(args.hms_project_dir, execute=True), indent=2, ensure_ascii=False, default=str))
            return 0
        if args.hms_command == "discover-dss":
            outputs = write_hms_dss_discovery_report(args.hms_project_dir)
            print(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "official-validation-summary":
            outputs = write_hms_official_validation_summary()
            print(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "precipitation-reference":
            copied, _ = ensure_reference_project()
            if copied is None:
                print("HEC-HMS precipitation reference status: reference_not_found")
                return 0
            result = analyze_reference_precipitation(copied)
            print(json.dumps({"status": "completed", "report_files": result["report_files"]}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "dss-backends":
            outputs = write_dss_backend_diagnosis()
            print(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "normalize-rainfall":
            print(json.dumps(write_normalized_rainfall_report(args.project_dir), indent=2, ensure_ascii=False, default=str))
            return 0
        if args.hms_command == "create-rainfall-project":
            result = create_hms_rainfall_verified_project(args.project_dir, args.output_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 1 if result["status"] == "rainfall_mapping_failed" else 0
        if args.hms_command == "write-rainfall-dss":
            result = write_project_rainfall_dss(args.project_dir, args.hms_project_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 1 if result["status"] == "failed" else 0
        if args.hms_command == "validate-rainfall-dss":
            result = validate_project_rainfall_dss(args.hms_project_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 1 if result["status"] == "failed" else 0
        if args.hms_command == "map-rainfall":
            result = map_project_rainfall(args.hms_project_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 1 if result["status"] == "failed" else 0
        if args.hms_command == "rainfall-open-probe":
            result = run_hms_rainfall_open_probe(args.hms_project_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 1 if result.get("status") != "project_opened" else 0
        if args.hms_command == "rainfall-gate":
            result = evaluate_hms_rainfall_gate(args.hms_project_dir)
            write_hms_rainfall_gate_report(args.hms_project_dir, result)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 1 if result["status"] == "failed" else 0
        if args.hms_command == "rainfall-compute":
            result = run_hms_rainfall_compute(args.hms_project_dir, timeout=120)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 1 if result["status"] in {"compute_failed", "compute_timeout"} else 0
        if args.hms_command == "result-catalog":
            outputs = write_hms_result_catalog_report(args.hms_project_dir)
            print(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "rainfall-validation-summary":
            outputs = write_rainfall_validation_summary(args.hms_project_dir)
            print(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "catalog-results":
            catalog = load_hms_result_catalog(Path(args.hms_project_dir) / "hydrolite_run.dss")
            print(json.dumps({"status": catalog.get("status"), "pathname_count": catalog["pathname_count"], "flow_pathname_count": catalog["flow_pathname_count"]}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "list-flow-results":
            catalog = load_hms_result_catalog(Path(args.hms_project_dir) / "hydrolite_run.dss")
            print(json.dumps({"flow_pathname_count": catalog["flow_pathname_count"], "flow_pathnames": catalog["flow_pathnames"]}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "read-flow-results":
            dss_path = Path(args.hms_project_dir) / "hydrolite_run.dss"
            catalog = load_hms_result_catalog(dss_path)
            result = read_hms_dss_timeseries(dss_path, catalog["flow_pathnames"], DEFAULT_RESULTS_DIR, timeout=60)
            result["catalog"] = catalog["classified"]
            result["requested_pathnames"] = catalog["flow_pathnames"]
            write_hms_timeseries_catalog(DEFAULT_RESULTS_DIR, result)
            print(json.dumps({key: result[key] for key in ("status", "backend", "requested_pathname_count", "successful_pathname_count", "failed_pathname_count", "runtime_seconds")}, indent=2, ensure_ascii=False))
            return 1 if result["status"] == "failed" else 0
        if args.hms_command == "map-results":
            catalog = load_hms_result_catalog(Path(args.hms_project_dir) / "hydrolite_run.dss")
            result = map_hms_results_to_hydrolite_elements(args.hms_project_dir, catalog, args.hydrolite_project_dir)
            outputs = write_hms_hydrolite_mapping_report(DEFAULT_RESULTS_DIR, result)
            print(json.dumps({"status": result["status"], "mapped_count": result["mapped_count"], "unmapped_count": result["unmapped_count"], "outputs": {key: str(value) for key, value in outputs.items()}}, indent=2, ensure_ascii=False))
            return 1 if result["status"] == "failed" else 0
        if args.hms_command == "identify-outlet":
            extraction = run_hms_result_extraction(args.hms_project_dir, DEFAULT_RESULTS_DIR)
            mapping = map_hms_results_to_hydrolite_elements(args.hms_project_dir, load_hms_result_catalog(Path(args.hms_project_dir) / "hydrolite_run.dss"), args.hydrolite_project_dir)
            outlet = select_verified_outlet_series(args.hms_project_dir, extraction["read_result"], mapping)
            outputs = write_outlet_selection_report(DEFAULT_RESULTS_DIR, outlet)
            print(json.dumps({"status": outlet.get("outlet_selection_status"), "candidates": outlet.get("candidates", []), "selected_outlet": outlet.get("selected_outlet"), "selected_pathname": outlet.get("selected_pathname"), "outputs": {key: str(value) for key, value in outputs.items()}}, indent=2, ensure_ascii=False))
            return 0
        if args.hms_command == "extract-results":
            result = run_hms_result_extraction(args.hms_project_dir, DEFAULT_RESULTS_DIR)
            print(json.dumps({"status": result["status"], "pathname_count": result["pathname_count"], "flow_pathname_count": result["flow_pathname_count"], "successful_pathname_count": result["read_result"]["successful_pathname_count"], "failed_pathname_count": result["read_result"]["failed_pathname_count"], "outlet_selection_status": result["outlet_selection"].get("outlet_selection_status"), "output_dir": str(DEFAULT_RESULTS_DIR)}, indent=2, ensure_ascii=False))
            return 1 if result["status"] == "failed" else 0
        if args.hms_command == "compare-hydrolite":
            result = run_hms_hydrolite_comparison(args.hms_project_dir, args.hydrolite_project_dir, DEFAULT_COMPARISON_DIR)
            print(json.dumps({"status": result["status"], "outlet": result.get("outlet_selection", {}).get("selected_outlet"), "alignment": result.get("alignment", {}), "comparison_metrics": result.get("comparison_metrics", {}), "event_differences": result.get("event_differences", {}), "output_dir": str(DEFAULT_COMPARISON_DIR)}, indent=2, ensure_ascii=False, default=str))
            return 1 if result["status"] in {"outlet_unresolved", "unit_unresolved", "alignment_failed"} else 0
        if args.hms_command == "comparison-report":
            path = write_hms_comparison_report(args.output_dir)
            print(f"HEC-HMS comparison report written to: {path}")
            return 0
        if args.hms_command == "comparison-bundle":
            path = export_hms_comparison_bundle(args.output_dir)
            print(f"HEC-HMS comparison bundle written to: {path}")
            return 0
        if args.hms_command == "validate-comparison":
            result = validate_hms_comparison_outputs(args.output_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["status"] == "failed" else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
