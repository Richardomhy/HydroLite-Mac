from dataclasses import replace

import pandas as pd
import pytest

from hydrolite.source_evidence import SourceEvidenceRecord, review_evidence, evidence_to_activity
from hydrolite.source_evidence_ledger import build_evidence_ledger
from hydrolite.source_evidence_scan import scan_source_evidence


def evidence(**kwargs):
    row = dict(evidence_id="e1", source_id="s1", evidence_type="discharge_flow", extracted_value=1.0, unit="m3/s", file_reference="anonymous.csv", row_reference="2", field_name="actual_flow", date_start="2026-01-01", date_end="2026-01-02", temporal_basis="period_mean", dataset_id="d1", measurement_role="outfall", provenance={"checksum": "fixture"})
    row.update(kwargs)
    return SourceEvidenceRecord(**row)


def confirmed(**kwargs):
    return review_evidence(evidence(**kwargs), "confirm", actor="tester", comment="Verified fixture")


def sources():
    return pd.DataFrame([{"source_id": "s1", "name": "anonymous", "source_type": "direct_outfall", "status": "accepted", "spatial_status": "unmapped"}])


def test_candidates_do_not_become_activity_and_confirmation_does():
    assert evidence_to_activity(evidence()) is None
    assert evidence_to_activity(confirmed()).value == 1
    assert review_evidence(evidence(), "reject", actor="a", comment="not source").status == "rejected"


@pytest.mark.parametrize("changes", [{"date_start": ""}, {"unit": "unknown"}, {"extracted_value": float("nan")}, {"source_id": ""}, {"provenance": {}}])
def test_invalid_confirmation(changes):
    with pytest.raises(ValueError): confirmed(**changes)


def test_design_capacity_is_not_flow():
    assert evidence_to_activity(confirmed(evidence_type="treatment_capacity")) is None
    assert evidence_to_activity(confirmed(field_name="design_capacity")) is None


def test_measured_ledger_bypasses_factor_and_does_not_invent_generation():
    ledger, _ = build_evidence_ledger(sources(), [confirmed(), confirmed(evidence_id="c1", evidence_type="measured_concentration", pollutant="TN", unit="mg/l", extracted_value=2)], [])
    row = ledger[ledger.pollutant.eq("TN")].iloc[0]
    assert row.net_emission_load == pytest.approx(172.8)
    assert pd.isna(row.generated_load) and pd.isna(row.removed_load)
    assert row.evidence_tier == "evidence_tier_1"
    assert ledger[ledger.pollutant.eq("TP")].net_emission_load.isna().all()


def test_reported_requires_reporting_authority_and_scope():
    item = confirmed(evidence_type="reported_pollutant_load", pollutant="TN", unit="kg/day", extracted_value=2)
    ledger, _ = build_evidence_ledger(sources(), [item], [])
    assert ledger.net_emission_load.isna().all()
    item = replace(item, provenance={**item.provenance, "reporting_authority": "anonymous", "load_scope": "source_emission"})
    ledger, _ = build_evidence_ledger(sources(), [item], [])
    assert ledger.loc[ledger.pollutant.eq("TN"), "net_emission_load"].iloc[0] == 2


def test_generic_multisheet_scan_and_read_only(tmp_path):
    import openpyxl
    path = tmp_path / "inputs.xlsx"
    book = openpyxl.Workbook(); sheet = book.active
    sheet.append(["project table"]); sheet.append(["source_id", "discharge_flow (m3/s)", "date"])
    sheet.append(["s1", 2, "2026-01-01"])
    hidden = book.create_sheet("hidden"); hidden.sheet_state = "hidden"
    hidden.append(["source_id", "人口(人)", "date"]); hidden.append(["s1", 10, "2026-01-01"])
    book.save(path); before = path.read_bytes()
    records, audit = scan_source_evidence(tmp_path, sources())
    assert any(e.evidence_type == "discharge_flow" and e.source_id == "s1" for e in records)
    assert any(e.provenance["sheet_visibility"] == "hidden" for e in records)
    assert all(not e.approved for e in records)
    assert path.read_bytes() == before and audit.status.eq("searched").any()
