import pandas as pd

from hydrolite.water_quality_features import find_upstream_water_quality_stations, map_stations_to_reaches, validate_station_graph_mapping


def _topology():
    mapping = pd.DataFrame({"station_id": ["WQ1", "WQ2"], "reach_id": ["R1", "R2"]})
    reaches = pd.DataFrame({"reach_id": ["R1", "R2"]})
    edges = pd.DataFrame([{"edge_id": "E1", "source_node": "R1", "target_node": "R2", "distance_km": 2.0}])
    return mapping, reaches, edges


def test_exact_mapping_and_true_upstream_relationship():
    stations, reaches, edges = _topology(); mapped = map_stations_to_reaches(stations, reaches)
    assert validate_station_graph_mapping(mapped, reaches)["status"] == "passed"
    assert mapped.mapping_confidence.eq("high").all()
    assert find_upstream_water_quality_stations(mapped, edges, "WQ2") == ["WQ1"]


def test_unresolved_mapping_is_excluded():
    stations, reaches, _ = _topology(); stations.loc[1, "reach_id"] = "missing"
    mapped = map_stations_to_reaches(stations, reaches, allow_fallback=False)
    assert mapped.loc[mapped.station_id == "WQ2", "mapping_status"].item() == "excluded"
    assert mapped.loc[mapped.station_id == "WQ2", "mapping_confidence"].item() == "low"


def test_single_reach_fallback_is_low_confidence_and_recorded():
    mapped = map_stations_to_reaches(pd.DataFrame({"station_id": ["WQ1"]}), pd.DataFrame({"reach_id": ["R1"]}))
    assert mapped.iloc[0].mapping_method == "single_reach_fallback"
    assert mapped.iloc[0].mapping_confidence == "low"
