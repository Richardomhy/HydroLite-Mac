import pytest

from hydrolite.graph_feature_benchmark import build_demo_graph
from hydrolite.river_graph import (
    RiverGraph,
    RiverGraphEdge,
    RiverGraphNode,
    calculate_downstream_nodes,
    calculate_topological_order,
    calculate_upstream_area,
    calculate_upstream_nodes,
    detect_graph_cycles,
    validate_river_graph,
)


def test_demo_graph_is_directed_dag_with_outlet():
    graph = build_demo_graph(); result = validate_river_graph(graph)
    assert result.status == "passed"
    assert result.cycles == []
    assert result.outlet_nodes == ["OUTLET"]
    assert result.disconnected_required_nodes == []
    assert calculate_topological_order(graph).index("R5") < calculate_topological_order(graph).index("OUTLET")


def test_upstream_downstream_and_area_follow_direction():
    graph = build_demo_graph()
    assert "S1" in calculate_upstream_nodes(graph, "OUTLET")
    assert "OUTLET" in calculate_downstream_nodes(graph, "S1")
    assert "OUTLET" not in calculate_upstream_nodes(graph, "S1")
    assert calculate_upstream_area(graph)["OUTLET"] == pytest.approx(sum(18 + i * 2 for i in range(1, 9)))


def test_cycle_is_reported_and_not_silently_deleted():
    graph = RiverGraph([RiverGraphNode("A", "reach"), RiverGraphNode("B", "reach"), RiverGraphNode("O", "outlet")], [RiverGraphEdge("AB", "A", "B"), RiverGraphEdge("BA", "B", "A"), RiverGraphEdge("BO", "B", "O")])
    assert detect_graph_cycles(graph)
    assert "invalid_hydrologic_cycle" in validate_river_graph(graph).errors
    with pytest.raises(ValueError, match="invalid_hydrologic_cycle"):
        calculate_topological_order(graph)


def test_missing_edge_node_and_disconnected_required_node_fail():
    graph = RiverGraph([RiverGraphNode("A", "subbasin", area_km2=1), RiverGraphNode("O", "outlet")], [RiverGraphEdge("AX", "A", "X")])
    result = validate_river_graph(graph)
    assert result.status == "failed"
    assert any(error.startswith("edge_node_missing") for error in result.errors)


def test_optional_disconnected_station_is_warning_only():
    graph = RiverGraph([RiverGraphNode("A", "subbasin", area_km2=1), RiverGraphNode("O", "outlet"), RiverGraphNode("ST", "monitoring_station")], [RiverGraphEdge("AO", "A", "O")])
    result = validate_river_graph(graph)
    assert result.status == "passed"
    assert result.warnings == ["disconnected_optional_station:ST"]
