from dataclasses import replace
import json

import pandas as pd
import pytest

from hydrolite.source_evidence import SourceEvidenceRecord, review_evidence
from hydrolite.point_source_evidence import audit_source_identity, audit_concentrations, classify_flow, temporal_alignment, factor_decision_records
from hydrolite.point_source_load import point_source_loads
from hydrolite.point_source_spatial import point_source_mapping, coordinate_audit


def sources():
    return pd.DataFrame([dict(source_id="s1", name="Anonymous outlet", source_type="direct_outfall", status="accepted", provenance="original record", geometry_type="point", longitude=.5, latitude=.5, spatial_status="unknown")])


def record(kind="measured_concentration", **changes):
    e = SourceEvidenceRecord("c1" if kind == "measured_concentration" else "f1", "s1", kind, file_reference="anonymous.xlsx", row_reference="2", field_name=kind, extracted_value=2, unit="mg/l" if kind == "measured_concentration" else "m3/s", date_start="2026-01-01", date_end="2026-01-01", temporal_basis="instantaneous", measurement_role="outfall_effluent", pollutant="TN" if kind == "measured_concentration" else "", provenance={"checksum": "abc", "flow_kind": "measured_flow"})
    return review_evidence(replace(e, **changes), "confirm", actor="fixture", comment="anonymous verified record")


def calculate(evidence):
    s = sources()
    return point_source_loads(s, audit_source_identity(s), evidence, [])


@pytest.mark.parametrize("field,expected", [("设计流量", "design_capacity"), ("许可流量", "permitted_capacity"), ("estimated_flow", "estimated_flow")])
def test_capacity_not_actual(field, expected):
    f = record("discharge_flow", field_name=field)
    assert classify_flow(f) == expected
    assert calculate([record(), f])[0].net_emission_load.isna().all()


@pytest.mark.parametrize("changes", [{"source_id": "different"}, {"date_start": "2026-02-01", "date_end": "2026-02-01"}])
def test_source_and_time_do_not_cross_join(changes):
    assert calculate([record(), record("discharge_flow", **changes)])[0].net_emission_load.isna().all()


@pytest.mark.parametrize("role", ["river_water", "wwtp_influent", "unknown"])
def test_non_effluent_not_load(role):
    assert not audit_concentrations([record(measurement_role=role)]).usable.any()
    assert calculate([record(measurement_role=role), record("discharge_flow")])[0].net_emission_load.isna().all()


@pytest.mark.parametrize("unit,value", [("m3/s", 1), ("m3/day", 86400)])
def test_measured_units(unit, value):
    ledger = calculate([record(), record("discharge_flow", unit=unit, extracted_value=value)])[0]
    row = ledger[ledger.pollutant.eq("TN")].iloc[0]
    assert row.net_emission_load == pytest.approx(172.8)
    assert pd.isna(row.generated_load) and pd.isna(row.removed_load)


def test_reported_semantics_and_disagreement():
    reported = record("reported_pollutant_load", evidence_id="r1", unit="kg/day", pollutant="TN", extracted_value=1)
    assert calculate([reported])[0].net_emission_load.isna().all()
    valid = replace(reported, provenance={**reported.provenance, "reporting_authority": "anonymous", "load_scope": "source_emission"})
    assert calculate([valid])[0].net_emission_load.notna().sum() == 1
    result = calculate([record(), record("discharge_flow"), valid])
    assert "material_disagreement" in set(result[-1].status)
    assert result[0].net_emission_load.isna().all()


def test_cod_not_codmn_and_duplicate_concentration():
    assert not audit_concentrations([record(pollutant="COD")]).usable.any()
    assert not audit_concentrations([record(), record(evidence_id="c2")]).usable.any()


def layers():
    import geopandas as gpd
    from shapely.geometry import Polygon, LineString
    return (gpd.GeoDataFrame({"subbasin_id": ["b1"]}, geometry=[Polygon([(0,0),(2,0),(2,2),(0,2)])], crs=3857), gpd.GeoDataFrame({"reach_id": ["r1"], "name": ["test river"], "subbasin_id": ["b1"]}, geometry=[LineString([(0,0),(0,2)])], crs=3857))


def test_crs_and_receiving_mapping():
    s = sources(); b, r = layers()
    coords, mapping = point_source_mapping(s, [], b, r)
    assert coords.coordinate_status.iloc[0] != "confirmed"
    assert not mapping.reach_confirmed.any()
    location = record("location", spatial_reference="EPSG:3857", provenance={"checksum": "abc", "coordinate_reference": "anonymous coordinate record"})
    water = record("receiving_water", extracted_value="test river")
    _, nearest = point_source_mapping(s, [location], b, r)
    assert not nearest.confidence.eq("high").any()
    _, mapped = point_source_mapping(s, [location, water], b, r)
    assert mapped.reach_confirmed.all() and mapped.subbasin_confidence.eq("high").all()
    _, conflict = point_source_mapping(s, [location, replace(water, extracted_value="unmatched river")], b, r)
    assert conflict.confidence.eq("conflicting").all() and not conflict.reach_confirmed.any()


def test_temporal_same_day_and_unknown():
    c = record(); f = record("discharge_flow", date_start="2026-01-01T12:00", date_end="2026-01-01T12:00")
    assert temporal_alignment(f, c) == "same_day"
    assert temporal_alignment(replace(f, date_end=""), c) == "unknown"


def test_factor_decision_never_approves():
    from hydrolite.emission_factor_approval import load_verified_candidates
    from hydrolite.water_environment import ROOT
    f, _ = load_verified_candidates(ROOT / "config/water_environment/factor_sources.yaml")
    decisions = factor_decision_records(f, [], "anonymous")
    assert len(decisions) == 12
    assert decisions.project_status.eq("decision_required").all()
    assert decisions.reviewer_action_required.all()


def test_geometry_metadata_is_not_coordinate_range():
    import geopandas as gpd
    from shapely.geometry import Point
    from hydrolite.point_source_spatial import coordinate_evidence_from_layer
    layer = gpd.GeoDataFrame({"source_id": ["s1"]}, geometry=[Point(.5, .5)], crs=3857)
    evidence = coordinate_evidence_from_layer(layer, sources(), reference="original.geojson", checksum="abc")
    assert len(evidence) == 1 and evidence[0].extraction_method == "confirmed_by_metadata"
    assert coordinate_audit(sources(), evidence).coordinate_status.eq("confirmed").all()
    layer = layer.set_crs(None, allow_override=True)
    assert coordinate_evidence_from_layer(layer, sources(), reference="original.geojson", checksum="abc") == []


def test_same_period_is_not_same_observation():
    c = record(date_start="2026-01-01", date_end="2026-01-03", temporal_basis="period_average")
    f = record("discharge_flow", date_start="2026-01-02", date_end="2026-01-04", temporal_basis="period_average")
    assert temporal_alignment(f, c) == "same_period"
    assert calculate([c, f])[0].net_emission_load.isna().all()


def test_period_volume_uses_actual_duration():
    c = record(date_start="2026-01-01", date_end="2026-01-03", temporal_basis="period_average")
    f = record("wastewater_volume", extracted_value=172800, unit="m3", date_start=c.date_start, date_end=c.date_end, temporal_basis=c.temporal_basis)
    row = calculate([c, f])[0].query("pollutant == 'TN'").iloc[0]
    assert row.net_emission_load == pytest.approx(172.8)


def test_conflicting_reports_do_not_fall_back_to_factor(monkeypatch):
    import hydrolite.point_source_load as module
    baseline = calculate([])[0]
    baseline.loc[baseline.pollutant.eq("TN"), "net_emission_load"] = 999
    monkeypatch.setattr(module, "build_evidence_ledger", lambda *args: (baseline.copy(), []))
    first = record("reported_pollutant_load", evidence_id="r1", pollutant="TN", unit="kg/day", provenance={"checksum": "abc", "reporting_authority": "anonymous", "load_scope": "source_emission"})
    second = replace(first, evidence_id="r2", extracted_value=3)
    assert calculate([first, second])[0].net_emission_load.isna().all()


def test_spatial_threshold_must_be_finite():
    b, r = layers()
    for value in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="finite and positive"):
            point_source_mapping(sources(), [], b, r, near_distance_m=value)


def test_capacity_type_cannot_be_overridden_by_flow_label():
    capacity = record("treatment_capacity", field_name="measured_flow")
    assert classify_flow(capacity) == "design_capacity"
    assert calculate([record(), capacity])[0].net_emission_load.isna().all()
