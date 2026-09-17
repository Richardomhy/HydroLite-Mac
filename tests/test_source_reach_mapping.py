import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Polygon

from hydrolite.source_reach_mapping import map_source_reaches
from hydrolite.source_evidence_readiness import evaluate_evidence_readiness, build_data_requests
from hydrolite.source_evidence_ledger import build_evidence_ledger


def layers():
    sources = pd.DataFrame([dict(source_id="s1", name="anon", source_type="direct_outfall", status="accepted", spatial_status="unmapped", longitude=10, latitude=20, geometry_type="point", receiving_water="river")])
    basins = gpd.GeoDataFrame({"subbasin_id": ["b1"]}, geometry=[Polygon([(0,0),(100,0),(100,100),(0,100)])], crs="EPSG:32649")
    rivers = gpd.GeoDataFrame({"name": ["river"], "reach_id": ["r1"]}, geometry=[LineString([(0,0),(0,100)])], crs=basins.crs)
    return sources, basins, rivers


def test_nearest_not_high_and_corroborated_mapping():
    s,b,r = layers(); s.receiving_water = ""
    mapping = map_source_reaches(s,b,r,source_crs=b.crs,coordinate_evidence="reviewed survey")
    assert mapping.confidence.iloc[0] == "low" and mapping.distance_m.iloc[0] == 10
    s.receiving_water = "river"
    assert map_source_reaches(s,b,r,source_crs=b.crs,coordinate_evidence="reviewed survey").confidence.iloc[0] == "high"


def test_administrative_only_and_missing_crs_do_not_map():
    s,b,r = layers(); s.geometry_type = "administrative"
    assert map_source_reaches(s,b,r,source_crs=b.crs).reach_id.isna().all()
    s.geometry_type = "point"
    assert map_source_reaches(s,b,r).reach_id.isna().all()


def test_geometry_without_reach_crosswalk_is_not_computational_reach():
    s,b,r = layers(); r = r.drop(columns="reach_id")
    result = map_source_reaches(s,b,r,source_crs=b.crs,coordinate_evidence="survey")
    assert result.reach_id.isna().all() and result.candidate_river_line.iloc[0] == "river"


def test_gate_and_data_requests_remain_honest():
    s,b,r = layers(); mapping = map_source_reaches(s,b,r,source_crs=b.crs)
    ledger,activities = build_evidence_ledger(s,[],[])
    gates,_,categories = evaluate_evidence_readiness(s,[],activities,[],mapping,ledger,"ready_with_warnings")
    assert gates["pollutant_delivery_model_gate"] == "blocked"
    assert "low_confidence_spatial_attribution" in gates["point_source_delivery_gate"]["blockers"]
    assert gates["basin_total_status"] == "not_reportable"
    assert categories[categories.category.eq("aquaculture")].status.iloc[0] == "unknown"
    requests = build_data_requests()
    assert {"point_sources","domestic","industrial","livestock","crop_agriculture","aquaculture"} <= set(requests.data_category)
