from dataclasses import replace
import json

import pandas as pd
import pytest

from hydrolite.point_source_completion import write_completion_template, ingest_point_source_completion_template, refresh_evidence, SHEETS
from tests.test_point_source_closure import sources, record, layers, calculate


def test_blank_template_and_candidate_import(tmp_path):
    p = write_completion_template(tmp_path / "with spaces.xlsx")
    assert pd.ExcelFile(p).sheet_names == list(SHEETS)
    records, errors, approvals = ingest_point_source_completion_template(p, sources())
    assert records == errors == approvals == []
    with pd.ExcelWriter(p, mode="a", engine="openpyxl", if_sheet_exists="replace") as writer:
        pd.DataFrame([{**{c: "" for c in SHEETS['排放水量']}, "source_id": "s1", "document_reference": "anonymous log", "value": 1, "unit": "m3/s", "flow_kind": "measured_flow"}]).to_excel(writer, sheet_name="排放水量", index=False)
    records, errors, _ = ingest_point_source_completion_template(p, sources())
    assert not errors and len(records) == 1 and not records[0].approved


def test_incremental_changed_and_missing(tmp_path, monkeypatch):
    p = tmp_path / "flow.csv"
    p.write_text("source_id,实际流量(m3/s),date\ns1,1,2026-01-01\n")
    first, index, audit, _ = refresh_evidence(tmp_path, sources(), [], paths=[p])
    assert audit[0]["status"] == "parsed" and first
    import hydrolite.point_source_completion as module
    original = module.scan_source_evidence
    monkeypatch.setattr(module, "scan_source_evidence", lambda *a, **k: pytest.fail("unchanged file parsed"))
    unchanged, index, audit, _ = refresh_evidence(tmp_path, sources(), first, index, paths=[p])
    assert audit[0]["status"] == "unchanged_skip"
    monkeypatch.setattr(module, "scan_source_evidence", original)
    p.write_text("source_id,实际流量(m3/s),date\ns1,2,2026-01-01\n")
    updated, index, audit, _ = refresh_evidence(tmp_path, sources(), unchanged, index, paths=[p])
    assert any(e.status == "superseded" for e in updated)
    p.unlink()
    missing, _, audit, _ = refresh_evidence(tmp_path, sources(), updated, index, paths=[p])
    assert any(e.status == "external_evidence_missing" for e in missing)


def test_no_evidence_and_point_eligibility_separate():
    from hydrolite.point_source_readiness import point_source_readiness
    from hydrolite.point_source_evidence import audit_source_identity
    from hydrolite.point_source_spatial import point_source_mapping
    from hydrolite.water_environment_contracts import POLLUTANTS
    s = sources(); b, r = layers()
    location = record("location", spatial_reference="EPSG:3857", provenance={"checksum": "abc", "coordinate_reference": "record"})
    water = record("receiving_water", extracted_value="test river")
    coords, mapped = point_source_mapping(s, [location, water], b, r)
    ev = [record(pollutant=p, evidence_id=p) for p in POLLUTANTS] + [record("discharge_flow")]
    ledger, flow, conc, align, _, _ = calculate(ev)
    closure, coverage, gates = point_source_readiness(s, audit_source_identity(s), coords, mapped, flow, conc, align, ledger, [])
    assert gates["point_source_m9b_eligibility"] == "eligible_with_warnings"
    assert gates["pollutant_delivery_model_gate"] == gates["diffuse_source_delivery_gate"] == "blocked"
    assert coverage["importance_weighted_coverage"] == "unavailable"
    with pytest.raises(ValueError, match="80%"):
        point_source_readiness(s, audit_source_identity(s), coords, mapped, flow, conc, align, ledger, [], thresholds={"minimum_quantified_coverage": .1})


def test_cli_ui_and_protected_paths():
    from hydrolite.__main__ import build_parser
    from hydrolite.point_source_workflow import point_output
    from hydrolite.water_environment import ROOT
    from hydrolite.ui.pages.water_environment_source_accounting import render_point_source_closure
    assert callable(render_point_source_closure)
    for cmd in ('point-source-status','point-source-map','point-source-load','data-request','evidence-refresh'):
        assert build_parser().parse_args(['water-environment',cmd]).water_environment_command == cmd
    for p in ('data_raw', 'tmp_emergency_0722', 'output/water_environment/m9a', 'output/water_environment/m9a1'):
        with pytest.raises(ValueError): point_output(ROOT / p)
