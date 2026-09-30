import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from hydrolite.project_measurement_intake import (
    TEMPLATES, generate_templates, list_requirements, measured_load_matches,
    refresh_measurement_gates, review_measurement_submission,
    submit_measurement_file, validate_measurement_file,
)
from hydrolite.workspace import create_workspace, read_workspace_manifest


def workspace(tmp_path):
    path = tmp_path / "project"
    create_workspace(path, "Anonymous test project")
    return path


def write_csv(path, rows, columns=None):
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
    return path


def accept(project, submission, monkeypatch):
    import hydrolite.project_versioning
    monkeypatch.setattr(hydrolite.project_versioning, "create_project_version", lambda *a, **k: {"project_version_id": "pv_test"})
    return review_measurement_submission(project, submission["submission_id"], "accept", reviewer="Reviewer A", comment="Checked against anonymous source record")


def test_six_versioned_templates_and_requirement_contract(tmp_path):
    project = workspace(tmp_path)
    result = generate_templates(project)
    assert len(TEMPLATES) == 6
    assert set(result["templates"]) == {"MR01", "MR02", "MR03", "MR04", "MR05", "MR06"}
    for key, spec in TEMPLATES.items():
        wb = pd.ExcelFile(result["templates"][key])
        assert "数据填写" in wb.sheet_names and "填写说明" in wb.sheet_names
        frame = pd.read_excel(result["templates"][key], sheet_name="数据填写", header=None)
        assert list(frame.iloc[0].dropna()) == spec["fields"]
        assert frame.iloc[1].notna().any() and frame.iloc[2].notna().any()
        assert validate_measurement_file(result["templates"][key], key)["status"] == "invalid"
    requirements = list_requirements(project)
    assert len(requirements["requirements"]) == 6
    assert requirements["summary"]["missing"] == 6


def test_missing_column_and_unknown_source_are_blocked(tmp_path):
    file = write_csv(tmp_path / "flow.csv", [{"source_id": "S-UNKNOWN", "flow": 1}])
    missing = validate_measurement_file(file, "MR02")
    assert missing["status"] == "invalid"
    assert any(row["rule"] == "required_column" and row["column"] == "timestamp" for row in missing["errors"])
    complete = write_csv(tmp_path / "flow_complete.csv", [{"source_id": "S-UNKNOWN", "timestamp": "2025-01-01T00:00:00", "flow": 1, "unit": "m3/s", "measurement_method": "meter", "flow_semantics": "measured_actual", "data_source": "log"}])
    result = validate_measurement_file(complete, "MR02", source_ids={"S-1"})
    assert result["status"] == "invalid"
    assert any(row["rule"] == "exact_source_id_match" for row in result["errors"])


def test_xlsx_chinese_header_rows_and_excel_row_location(tmp_path):
    from openpyxl import Workbook
    from hydrolite.project_measurement_intake import TEMPLATES

    path = tmp_path / "flow.xlsx"
    book = Workbook(); sheet = book.active; sheet.title = "流量记录"
    sheet.append(["高桥河排口流量记录"]); sheet.append([])
    sheet.append(TEMPLATES["MR02"]["labels"]); sheet.append([])
    sheet.append(["S1", "2025-01-01T00:00:00", -1, "m3/s", "meter", "measured_actual", "field log"])
    book.save(path)
    result = validate_measurement_file(path, "MR02", source_ids={"S1"})
    assert result["status"] == "invalid"
    error = next(row for row in result["errors"] if row["rule"] == "finite_nonnegative_value")
    assert error["sheet"] == "流量记录" and error["row"] == 5


def test_negative_concentration_and_qualifier_are_distinguished(tmp_path):
    bad = write_csv(tmp_path / "negative.csv", [{"source_id": "S1", "timestamp": "2025-01-01", "pollutant": "TN", "concentration": -1, "unit": "mg/L", "sample_type": "grab", "quality_flag": "ok"}])
    assert validate_measurement_file(bad, "MR03")["status"] == "invalid"
    qualified = write_csv(tmp_path / "qualified.csv", [{"source_id": "S1", "timestamp": "2025-01-01T00:00:00", "pollutant": "TN", "concentration": "<0.05", "unit": "mg/L", "sample_type": "grab", "detection_limit": "0.05", "quality_flag": "below_dl"}])
    assert validate_measurement_file(qualified, "MR03")["status"] == "review_required"


def test_detection_limit_is_not_replaced_by_a_numeric_concentration(tmp_path, monkeypatch):
    project = workspace(tmp_path)
    qualified = write_csv(tmp_path / "qualified.csv", [{"source_id": "S1", "timestamp": "2025-01-01T00:00:00", "pollutant": "TN", "concentration": "<0.05", "unit": "mg/L", "sample_type": "grab", "detection_limit": "0.05", "quality_flag": "below_dl"}])
    submission = submit_measurement_file(qualified, project, "MR03", source_ids={"S1"})
    review = accept(project, submission, monkeypatch)
    assert review["gate_refresh"]["manual_ready_override"] is False
    accepted = next(row for row in json.loads((project / "measurements/measurement_manifest.json").read_text())["submissions"] if row["submission_id"] == submission["submission_id"])
    normalized = pd.read_csv(project / accepted["normalized_path"])
    assert pd.isna(normalized.loc[0, "value"])
    assert normalized.loc[0, "qualifier"] == "<"
    assert normalized.loc[0, "detection_limit_mg_l"] == 0.05


def test_detection_limit_unit_is_normalized_without_substitution(tmp_path, monkeypatch):
    project = workspace(tmp_path)
    file = write_csv(tmp_path / "qualified_ug.csv", [{"source_id": "S1", "timestamp": "2025-01-01T00:00:00", "pollutant": "TN", "concentration": "<50", "unit": "ug/L", "sample_type": "grab", "detection_limit": "50", "quality_flag": "below_dl"}])
    submission = submit_measurement_file(file, project, "MR03", source_ids={"S1"})
    accept(project, submission, monkeypatch)
    accepted = next(row for row in json.loads((project / "measurements/measurement_manifest.json").read_text())["submissions"] if row["submission_id"] == submission["submission_id"])
    normalized = pd.read_csv(project / accepted["normalized_path"])
    assert pd.isna(normalized.loc[0, "value"])
    assert normalized.loc[0, "qualifier"] == "<"
    assert normalized.loc[0, "detection_limit_mg_l"] == 0.05


def test_duplicate_sha_immutable_original_review_and_snapshot_only_on_accept(tmp_path, monkeypatch):
    project = workspace(tmp_path)
    flow = write_csv(tmp_path / "flow.csv", [{"source_id": "ANON-A", "timestamp": "2025-01-01T00:00:00", "flow": 0.2, "unit": "m3/s", "measurement_method": "meter", "flow_semantics": "measured_actual", "data_source": "anonymous demo"}])
    first = submit_measurement_file(flow, project, "MR02", source_ids={"ANON-A"})
    raw = project / first["original_path"]
    assert raw.stat().st_mode & 0o222 == 0
    duplicate = submit_measurement_file(flow, project, "MR02", source_ids={"ANON-A"})
    assert duplicate["status"] == "duplicate_submission"
    calls = []
    import hydrolite.project_versioning
    monkeypatch.setattr(hydrolite.project_versioning, "create_project_version", lambda *a, **k: calls.append(k) or {"project_version_id": "pv_test"})
    review_measurement_submission(project, first["submission_id"], "reject", reviewer="Reviewer A", comment="Rejected anonymous test record")
    assert not calls
    revised = write_csv(tmp_path / "flow_revised.csv", [{"source_id": "ANON-A", "timestamp": "2025-01-01T00:00:00", "flow": 0.21, "unit": "m3/s", "measurement_method": "meter", "flow_semantics": "measured_actual", "data_source": "anonymous demo revision"}])
    second = submit_measurement_file(revised, project, "MR02", source_ids={"ANON-A"})
    review_measurement_submission(project, second["submission_id"], "accept", reviewer="Reviewer A", comment="Checked against anonymous source record")
    assert calls and raw.read_bytes() == flow.read_bytes()
    manifest = read_workspace_manifest(project)
    assert manifest["datasets"][-1]["project_measurement_confirmed"] is True


def test_matched_and_unmatched_periods_and_design_flow(tmp_path, monkeypatch):
    project = workspace(tmp_path)
    flow = write_csv(tmp_path / "flow.csv", [{"source_id": "ANON-A", "timestamp": "2025-01-01T00:00:00", "flow": 0.2, "unit": "m3/s", "measurement_method": "meter", "flow_semantics": "measured_actual", "data_source": "synthetic only"}, {"source_id": "ANON-B", "timestamp": "2025-01-01T00:00:00", "flow": 100, "unit": "m3/s", "measurement_method": "design", "flow_semantics": "design_capacity", "data_source": "synthetic only"}])
    concentration = write_csv(tmp_path / "conc.csv", [{"source_id": "ANON-A", "timestamp": "2025-01-01T00:00:00", "pollutant": "TN", "concentration": 2, "unit": "mg/L", "sample_type": "composite", "quality_flag": "ok"}, {"source_id": "ANON-A", "timestamp": "2025-01-02T00:00:00", "pollutant": "TP", "concentration": 1, "unit": "mg/L", "sample_type": "composite", "quality_flag": "ok"}])
    f = submit_measurement_file(flow, project, "MR02", source_ids={"ANON-A", "ANON-B"})
    c = submit_measurement_file(concentration, project, "MR03", source_ids={"ANON-A", "ANON-B"})
    accept(project, f, monkeypatch); accept(project, c, monkeypatch)
    matches = measured_load_matches(project)
    assert [(m["source_id"], m["pollutant"]) for m in matches] == [("ANON-A", "TN")]
    assert all(m["status"] == "measured_load_ready" for m in matches)
    dataset = next(row for row in read_workspace_manifest(project)["datasets"] if row["submission_id"] == f["submission_id"])
    assert dataset["quality_status"] == "ready_with_warnings" and dataset["project_measurement_confirmed"]
    standardized = pd.read_csv(project / dataset["standardized_path"])
    assert standardized.source_id.tolist() == ["ANON-A"]
    assert not any(row["source_id"] == "ANON-B" for row in matches)


def test_unknown_crs_and_reach_require_human_confirmation(tmp_path, monkeypatch):
    project = workspace(tmp_path)
    coords = write_csv(tmp_path / "coords.csv", [{"source_id": "S1", "source_name": "Outfall", "longitude": 114.1, "latitude": 22.6, "crs": "GCJ-02", "coordinate_source": "survey", "survey_date": "2025-01-01", "notes": "synthetic"}])
    result = validate_measurement_file(coords, "MR01", source_ids={"S1"})
    assert result["status"] == "review_required"
    assert any(row["rule"] == "crs_human_review" for row in result["errors"])
    relation = write_csv(tmp_path / "reach.csv", [{"source_id": "S1", "receiving_water": "River", "reach_id": "R-nearest", "evidence_type": "nearest reach", "confirmation": "unconfirmed", "notes": "candidate only"}])
    submitted = submit_measurement_file(relation, project, "MR04", source_ids={"S1"})
    assert submitted["status"] == "needs_review"
    with pytest.raises(ValueError, match="human confirmation"):
        review_measurement_submission(project, submitted["submission_id"], "accept", reviewer="Reviewer A", comment="Not yet confirmed")


def test_resolver_refresh_audit_and_output_reports(tmp_path, monkeypatch):
    project = workspace(tmp_path)
    flow = write_csv(tmp_path / "flow.csv", [{"source_id": "S1", "timestamp": "2025-01-01T00:00:00", "flow": 1, "unit": "m3/s", "measurement_method": "meter", "flow_semantics": "measured_actual", "data_source": "anonymous"}])
    before = refresh_measurement_gates(project)
    submission = submit_measurement_file(flow, project, "MR02", source_ids={"S1"})
    review = accept(project, submission, monkeypatch)
    assert review["gate_refresh"]["transitions"]
    after = _manifest = json.loads((project / "measurements/measurement_manifest.json").read_text())["gate_refreshes"][-1]
    assert after["manual_ready_override"] is False
    assert any(row["requirement_id"] == "DR02" and row["new_status"] == "local_ready" for row in after["transitions"])
    assert after["existing_m9a2_gate_engine"]["status"].startswith("skipped_")
    outputs = __import__("hydrolite.project_measurement_intake", fromlist=["write_measurement_intake_reports"]).write_measurement_intake_reports(project, tmp_path / "out")
    assert all(Path(path).is_file() for path in outputs.values())


def test_upload_security_and_unavailable_workspace(tmp_path):
    macro = tmp_path / "macro.xlsm"; macro.write_bytes(b"not a workbook")
    assert validate_measurement_file(macro, "MR01")["status"] == "invalid"
    unsafe = tmp_path / "external.xlsx"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/externalLinks/externalLink1.xml", "<externalLink/>")
    assert validate_measurement_file(unsafe, "MR01")["status"] == "invalid"
    traversal = tmp_path / "traversal.xlsx"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("../outside.xml", "not extracted")
    assert validate_measurement_file(traversal, "MR01")["status"] == "invalid"
    with pytest.raises(OSError, match="project_storage_unavailable"):
        submit_measurement_file(macro, tmp_path / "not-mounted", "MR01")


def test_audit_workbook_keeps_uploaded_text_as_literal(tmp_path):
    from openpyxl import load_workbook
    from hydrolite.project_measurement_intake import write_measurement_intake_reports

    project = workspace(tmp_path)
    file = write_csv(tmp_path / "identity.csv", [{"source_id": "=1+1", "source_name": "test", "longitude": 0, "latitude": 0, "crs": "WGS84", "coordinate_source": "test", "survey_date": "2025-01-01"}])
    submitted = submit_measurement_file(file, project, "MR01")
    review_measurement_submission(project, submitted["submission_id"], "reject", reviewer="Reviewer", comment="=HYPERLINK(\"https://example.invalid\")")
    result = write_measurement_intake_reports(project, tmp_path / "reports")
    workbook = load_workbook(result["review"], data_only=False)
    cell = workbook["reviews"]["E2"]
    assert cell.data_type != "f" and str(cell.value).startswith("'")


def test_ui_page_and_workflow_extension_import():
    from importlib import import_module
    page = import_module("hydrolite.ui.pages.project_measurement_intake")
    from hydrolite.workflow_engine import get_workflow_stage
    assert callable(page.render)
    assert get_workflow_stage("project_measurement_intake")["status"] == "partial"
