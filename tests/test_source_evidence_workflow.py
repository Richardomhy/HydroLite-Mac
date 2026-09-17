from pathlib import Path
import subprocess
import sys

import pytest

from hydrolite.source_evidence_workflow import checked_output, _save_state, record_review, read_evidence_state
from tests.test_source_evidence import evidence


def test_protected_output_and_symlink_rejected(tmp_path):
    from hydrolite.provenance import ROOT
    for name in ("data_raw", "tmp_emergency_0722", "output/water_environment/m9a"):
        with pytest.raises(ValueError): checked_output(ROOT / name)
    alias = tmp_path / "external volume link"; alias.symlink_to(ROOT / "data_raw")
    with pytest.raises(ValueError): checked_output(alias)
    assert checked_output(tmp_path / "volume with spaces") == tmp_path / "volume with spaces"


def test_review_persists_and_audits_without_touching_source(monkeypatch, tmp_path):
    monkeypatch.setenv("HYDROLITE_RUNTIME_DIR", str(tmp_path / "runtime"))
    root = tmp_path / "output"
    _save_state(root, {"project_id": "anonymous", "evidence": [evidence().as_dict()], "factors": [], "approvals": []})
    result = record_review(root, "e1", "confirm", actor="test", comment="verified")
    assert result["outputs_stale"]
    assert read_evidence_state(root)["evidence"][0]["status"] == "confirmed"
    from hydrolite.runtime_db import list_audit_event_records
    assert list_audit_event_records(project_id="anonymous")[0]["object_id"] == "e1"
    (root / "reports").mkdir()
    (root / "reports/m9a1_manifest.json").write_text('{"project_version": "frozen"}')
    before = (root / "review_state.json").read_bytes()
    with pytest.raises(ValueError, match="immutable"):
        record_review(root, "e1", "reject", actor="test", comment="not allowed")
    assert (root / "review_state.json").read_bytes() == before


def test_new_cli_and_registry_are_scoped(tmp_path):
    from hydrolite.capability_registry import get_capability
    from hydrolite.workflow_engine import get_workflow_stage
    from hydrolite.run_recipes import get_run_recipe
    result = subprocess.run([sys.executable, "-m", "hydrolite", "water-environment", "evidence-review", "--output-dir", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1 and "output_missing" in result.stdout
    assert get_capability("water_quality")["status"] == "planned"
    assert get_workflow_stage("source_evidence_completion")["status"] == "partial"
    assert get_run_recipe("water_environment_evidence_closure")["stages"][0] == "source_evidence_completion"


def test_ui_empty_state_import_and_render(tmp_path):
    from streamlit.testing.v1 import AppTest
    script = f"from hydrolite.ui.pages.water_environment_source_accounting import render_evidence_completion\nrender_evidence_completion({str(tmp_path)!r})"
    app = AppTest.from_string(script).run(timeout=15)
    assert not app.exception


def test_missing_external_directory_fails_before_output(tmp_path):
    from hydrolite.source_evidence_workflow import run_evidence_closure
    missing = tmp_path / "volume missing"; output = tmp_path / "output"
    with pytest.raises(FileNotFoundError, match="external_project_storage_unavailable"):
        run_evidence_closure(missing, output_dir=output)
    assert not output.exists()
