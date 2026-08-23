from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from tests.runtime_helpers import configure_runtime


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    pd.DataFrame({
        "采样点编号": ["A-01", "A-02"],
        "高锰酸盐指数(mg/L)": [2.1, None],
        "氨氮(mg/L)": [0.2, 0.3],
        "总氮(mg/L)": [1.0, 1.2],
        "总磷(mg/L)": [0.1, 0.2],
    }).to_csv(root / "water_quality.csv", index=False)
    pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="h"),
        "rain_mm": [0, 5, 2, 0], "flow_m3_s": [1, 2, 3, 2], "water_level_m": [1.0, 1.1, 1.2, 1.1],
    }).to_csv(root / "rainfall_flow.csv", index=False)
    pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="h"),
        "flow_obs_m3_s": [1, 2, 3, 2], "flow_sim_m3_s": [1.1, 1.8, 2.7, 2.1],
    }).to_csv(root / "observed_simulated_flow.csv", index=False)
    (root / "watershed_boundary.geojson").write_text(json.dumps({
        "type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]
    }), encoding="utf-8")
    (root / "unclassified.bin").write_bytes(b"anonymous")
    return root


def test_real_project_inventory_qc_and_mapping_are_read_only(tmp_path):
    from hydrolite.real_project import audit_data_quality, discover_real_project_data

    source = _source(tmp_path)
    before = {path.name: path.read_bytes() for path in source.iterdir()}
    inventory, paths = discover_real_project_data(source)
    quality, mapping, units, spatial, tables = audit_data_quality(inventory, paths)
    assert len(inventory) == 5
    assert set(inventory["registered_status"]) >= {"referenced", "not_registered"}
    assert {"CODMn", "NH3-N", "TN", "TP"} <= set(mapping["canonical_field"])
    assert "mg/L" in set(units["detected_unit"])
    assert set(units.loc[units["field"] == "timestamp", "detected_unit"]) <= {"not_applicable"}
    assert not spatial.empty and len(tables) >= 3
    assert before == {path.name: path.read_bytes() for path in source.iterdir()}


def test_real_project_status_and_commercial_gate(tmp_path):
    from hydrolite.real_project import (
        analyze_hydrology_diagnostic, analyze_water_quality, analyze_wet_weather_event,
        assess_real_project_commercial_readiness, audit_data_quality,
        build_capability_readiness, discover_real_project_data,
    )

    inventory, paths = discover_real_project_data(_source(tmp_path))
    _, _, _, _, tables = audit_data_quality(inventory, paths)
    _, wq = analyze_water_quality(tables)
    _, event = analyze_wet_weather_event(tables, wq)
    _, hydro = analyze_hydrology_diagnostic(tables)
    readiness = build_capability_readiness(inventory, wq, event, hydro)
    commercial = assess_real_project_commercial_readiness(readiness)
    assert wq["status"] == "real_data_tested"
    assert hydro["status"] == "real_data_diagnostic"
    assert readiness.set_index("capability").loc["water_quality_method_lab", "data_readiness"] == "experimental"
    assert readiness.set_index("capability").loc["flood_forecast", "data_readiness"] == "blocked"
    assert commercial["commercial_beta_blocker"].any()


def test_nested_workspace_identity_and_real_baseline_status(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.project_service import register_workspace_as_project
    from hydrolite.project_versioning import create_project_version
    from hydrolite.workspace import create_workspace

    workspace = tmp_path / "workspace"
    create_workspace(workspace, "Nested Identity")
    project = register_workspace_as_project(workspace)
    version = create_project_version(project["project_id"], status="real_project_baseline")
    assert project["name"] == "Nested Identity"
    assert project["project_id"] == "nested_identity"
    assert version["status"] == "real_project_baseline"


def test_real_project_audit_writes_sanitized_governed_outputs(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.real_project import OUTPUT_NAMES, run_real_project_audit

    source = _source(tmp_path)
    result = run_real_project_audit(
        source, workspace_dir=tmp_path / "workspace", output_dir=tmp_path / "output",
        project_name="Anonymous Real Validation",
    )
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert result["version"]["status"] == "real_project_baseline"
    assert result["deliverable"]["review_status"] == "reviewed"
    assert result["integrity"]["status"] == "passed"
    assert manifest["real_project"] is True
    assert str(tmp_path) not in json.dumps(manifest)
    assert manifest["capabilities_executed"] == ["historical_flood_analysis", "water_quality_data_analysis"]
    for key in ("inventory", "quality", "readiness", "validation", "friction", "manifest"):
        assert (tmp_path / "output" / OUTPUT_NAMES[key]).is_file()


def test_real_project_ui_and_registry_contract():
    from hydrolite.capability_registry import get_capability
    from hydrolite.scenario_registry import get_scenario
    from hydrolite.ui.pages.real_project_baseline import find_real_project_baseline, load_real_project_baseline

    assert callable(load_real_project_baseline)
    assert get_capability("water_quality")["status"] == "planned"
    assert get_capability("water_quality_data_analysis")["status"] == "available"
    assert get_scenario("SC06").capabilities == ("water_quality_data_analysis",)
    assert callable(find_real_project_baseline)


def test_real_project_ui_follows_workspace_pointer(tmp_path):
    from hydrolite.ui.pages.real_project_baseline import build_ui_closure, find_real_project_baseline
    from hydrolite.ui.state import WorkbenchContext

    output = tmp_path / "audit-output"
    output.mkdir()
    workspace = tmp_path / "workspace"
    (workspace / "reports").mkdir(parents=True)
    (workspace / "reports" / "real_project_baseline_pointer.json").write_text(
        json.dumps({"output_dir": str(output)}), encoding="utf-8"
    )
    context = WorkbenchContext(
        workspace, True, True, {}, "Project", "project", {}, [], False, False, "", False, "", {}, {}, ""
    )
    assert find_real_project_baseline(context) == output
    (output / "reports").mkdir()
    (output / "reports" / "m8a_real_project_manifest.json").write_text(
        json.dumps({"integrity_status": "passed", "delivery_review_status": "reviewed"}), encoding="utf-8"
    )
    closure = build_ui_closure(context, output, {"数据清单": pd.DataFrame(), "能力就绪度": pd.DataFrame(), "真实验证": pd.DataFrame()})
    assert set(closure["状态"]) == {"passed", "warning"}


def test_real_project_ui_prefers_m8b_actual_status(tmp_path):
    from hydrolite.ui.pages.real_project_baseline import (
        build_real_project_summary, build_ui_closure, load_real_project_baseline,
    )
    from hydrolite.ui.pages.results_center import _real_m8b_payload
    from hydrolite.ui.state import WorkbenchContext

    output = tmp_path / "audit-output"
    workspace = tmp_path / "workspace"
    (workspace / "reports").mkdir(parents=True)
    (workspace / "reports" / "real_project_baseline_pointer.json").write_text(
        json.dumps({"output_dir": str(output)}), encoding="utf-8"
    )
    for relative in (
        "m8b/basin/basin_summary.xlsx",
        "m8b/inputs/parameter_provenance.xlsx",
        "m8b/events/event_readiness.xlsx",
        "m8b/validation/validation_summary.xlsx",
        "m8b/scenarios/scenario_comparison.xlsx",
    ):
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"status": ["passed"]}).to_excel(path, index=False)
    manifest = {
        "real_project": True,
        "project_version": "pv_version_2",
        "actual_hydrolite_run_ids": ["run_actual"],
        "scientific_status": "real_data_diagnostic",
        "scenario_type": "what_if_sensitivity_scenario",
        "delivery_review_status": "reviewed",
        "integrity_status": "passed",
        "warnings": ["single_event_diagnostic"],
    }
    manifest_path = output / "m8b/reports/m8b_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    context = WorkbenchContext(
        workspace, True, True, {"project": {"real_project": True}}, "Project", "project", {}, [],
        False, False, "", False, "", {}, {}, "",
    )

    tables = load_real_project_baseline(output)
    summary = build_real_project_summary(manifest)
    closure = build_ui_closure(context, output, tables).set_index("环节")["状态"]
    payload = _real_m8b_payload(context)
    assert {"流域与拓扑", "真实运行验证", "情景对比"} <= tables.keys()
    assert summary == {
        "Project Version": "pv_version_2", "HydroLite Real Run": "run_actual",
        "Scientific Validation": "real_data_diagnostic", "Scenario": "what_if_sensitivity_scenario",
        "Delivery": "reviewed",
    }
    assert closure["Run"] == "passed" and closure["Results"] == "warning" and closure["Delivery"] == "passed"
    assert payload and payload[1]["Scientific Validation"] == "real_data_diagnostic"


def test_build_and_run_entrypoints_exist():
    root = Path(__file__).resolve().parents[1]
    script = root / "script" / "build_and_run.sh"
    environment = root / ".codex" / "environments" / "environment.toml"
    assert script.is_file() and script.stat().st_mode & 0o111
    script_text = script.read_text(encoding="utf-8")
    assert 'command = "./script/build_and_run.sh"' in environment.read_text(encoding="utf-8")
    assert "wait_for_shutdown" in script_text and "pkill -KILL" in script_text
