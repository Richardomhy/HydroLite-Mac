"""Dependency-light directed river graph primitives for HydroLite.

The graph is always directed from upstream to downstream.  It carries topology
and provenance only; it does not alter HydroLite routing or water-balance state.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


NODE_TYPES = {"subbasin", "reach", "monitoring_station", "reservoir", "outlet", "water_quality_station"}
EDGE_TYPES = {"upstream_downstream", "tributary", "subbasin_to_reach", "reach_to_station", "reservoir_release", "station_context"}


@dataclass(slots=True)
class RiverGraphNode:
    node_id: str
    node_type: str
    name: str = ""
    geometry_reference: str | None = None
    area_km2: float | None = None
    reach_id: str | None = None
    subbasin_id: str | None = None
    station_id: str | None = None
    reservoir_id: str | None = None
    upstream_area_km2: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.node_id = str(self.node_id)
        if self.node_type not in NODE_TYPES:
            raise ValueError(f"Unsupported river graph node_type: {self.node_type}")


@dataclass(slots=True)
class RiverGraphEdge:
    edge_id: str
    source_node: str
    target_node: str
    edge_type: str = "upstream_downstream"
    direction: str = "upstream_to_downstream"
    distance_km: float | None = None
    travel_time: float | None = None
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.edge_id = str(self.edge_id)
        self.source_node = str(self.source_node)
        self.target_node = str(self.target_node)
        if self.edge_type not in EDGE_TYPES:
            raise ValueError(f"Unsupported river graph edge_type: {self.edge_type}")
        if self.direction != "upstream_to_downstream":
            raise ValueError("River graph edges must use upstream_to_downstream direction")
        if self.weight < 0:
            raise ValueError("River graph edge weight must be nonnegative")


@dataclass(slots=True)
class RiverGraph:
    nodes: list[RiverGraphNode]
    edges: list[RiverGraphEdge]
    directed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.directed:
            raise ValueError("HydroLite river graphs must be directed")

    def as_dict(self) -> dict[str, Any]:
        return {"nodes": [asdict(item) for item in self.nodes], "edges": [asdict(item) for item in self.edges], "directed": True, "metadata": self.metadata}


@dataclass(slots=True)
class RiverGraphValidationResult:
    status: str
    errors: list[str]
    warnings: list[str]
    cycles: list[list[str]]
    topological_order: list[str]
    disconnected_required_nodes: list[str]
    outlet_nodes: list[str]
    upstream_area_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_graph(graph: RiverGraph | Mapping[str, Any]) -> RiverGraph:
    if isinstance(graph, RiverGraph):
        return graph
    raw_nodes = graph.get("nodes", [])
    nodes = [item if isinstance(item, RiverGraphNode) else RiverGraphNode(node_id=item, node_type=graph.get("node_type", "reach")) if isinstance(item, str) else RiverGraphNode(**item) for item in raw_nodes]
    edges: list[RiverGraphEdge] = []
    for index, item in enumerate(graph.get("edges", []), 1):
        if isinstance(item, RiverGraphEdge):
            edges.append(item)
        elif isinstance(item, (tuple, list)):
            edges.append(RiverGraphEdge(f"E{index}", item[0], item[1]))
        else:
            edges.append(RiverGraphEdge(**item))
    return RiverGraph(nodes, edges, bool(graph.get("directed", True)), dict(graph.get("metadata", {})))


def _node_ids(graph: RiverGraph | Mapping[str, Any]) -> list[str]:
    return [node.node_id for node in _coerce_graph(graph).nodes]


def _pairs(graph: RiverGraph | Mapping[str, Any], include_context: bool = True) -> list[tuple[str, str]]:
    result = []
    for edge in _coerce_graph(graph).edges:
        if include_context or edge.edge_type != "station_context":
            result.append((edge.source_node, edge.target_node))
    return result


def build_graph_from_reaches(reaches: Any) -> RiverGraph:
    frame = pd.DataFrame(reaches).copy()
    nodes = [RiverGraphNode(str(row.reach_id), "reach", reach_id=str(row.reach_id), metadata={"source": "reach_table"}) for row in frame.itertuples()]
    edges: list[RiverGraphEdge] = []
    for row in frame.to_dict("records"):
        source = row.get("reach_id") or row.get("upstream_reach_id")
        target = row.get("downstream_reach_id")
        if pd.notna(source) and pd.notna(target) and str(target).strip():
            edges.append(RiverGraphEdge(str(row.get("edge_id") or f"reach_{source}_{target}"), str(source), str(target), "upstream_downstream", distance_km=_optional_float(row.get("distance_km")), travel_time=_optional_float(row.get("travel_time")), metadata={"travel_time_method": row.get("travel_time_method", "configured") if pd.notna(row.get("travel_time", np.nan)) else "topological_fallback"}))
    known = {node.node_id for node in nodes}
    for value in sorted({item for pair in [(edge.source_node, edge.target_node) for edge in edges] for item in pair} - known):
        nodes.append(RiverGraphNode(value, "reach", reach_id=value, metadata={"source": "topology_reference"}))
    return RiverGraph(nodes, edges, metadata={"builder": "build_graph_from_reaches"})


def build_graph_from_subbasins(subbasins: Any, downstream_column: str = "downstream_subbasin_id") -> RiverGraph:
    frame = pd.DataFrame(subbasins).copy()
    nodes = [RiverGraphNode(str(row["subbasin_id"]), "subbasin", name=str(row.get("name", "")), area_km2=_optional_float(row.get("area_km2")), subbasin_id=str(row["subbasin_id"]), reach_id=_optional_str(row.get("reach_id")), provenance={"source": "subbasin_table"}) for row in frame.to_dict("records")]
    edges = []
    for row in frame.to_dict("records"):
        target = row.get(downstream_column)
        if pd.notna(target) and str(target).strip():
            edges.append(RiverGraphEdge(f"subbasin_{row['subbasin_id']}_{target}", str(row["subbasin_id"]), str(target), "tributary"))
    return RiverGraph(nodes, edges, metadata={"builder": "build_graph_from_subbasins"})


def build_graph_from_topology(nodes: Any, edges: Any, metadata: Mapping[str, Any] | None = None) -> RiverGraph:
    node_rows = pd.DataFrame(nodes).to_dict("records") if not isinstance(nodes, list) or not all(isinstance(x, RiverGraphNode) for x in nodes) else nodes
    edge_rows = pd.DataFrame(edges).to_dict("records") if not isinstance(edges, list) or not all(isinstance(x, RiverGraphEdge) for x in edges) else edges
    built_nodes = [item if isinstance(item, RiverGraphNode) else RiverGraphNode(**item) for item in node_rows]
    built_edges = [item if isinstance(item, RiverGraphEdge) else RiverGraphEdge(**item) for item in edge_rows]
    return RiverGraph(built_nodes, built_edges, metadata=dict(metadata or {}))


def add_monitoring_stations(graph: RiverGraph | Mapping[str, Any], stations: Any) -> RiverGraph:
    result = _coerce_graph(graph)
    nodes, edges = list(result.nodes), list(result.edges)
    for row in pd.DataFrame(stations).to_dict("records"):
        station_id = str(row["station_id"]); node_id = str(row.get("node_id") or station_id); reach_id = str(row["reach_id"])
        nodes.append(RiverGraphNode(node_id, "monitoring_station", name=str(row.get("name", "")), reach_id=reach_id, station_id=station_id, metadata={"required": bool(row.get("required", False))}))
        edges.append(RiverGraphEdge(f"station_{reach_id}_{node_id}", reach_id, node_id, "reach_to_station"))
    return RiverGraph(nodes, edges, metadata=result.metadata)


def add_reservoir_nodes(graph: RiverGraph | Mapping[str, Any], reservoirs: Any) -> RiverGraph:
    result = _coerce_graph(graph); nodes, edges = list(result.nodes), list(result.edges)
    for row in pd.DataFrame(reservoirs).to_dict("records"):
        node_id = str(row.get("node_id") or row["reservoir_id"])
        nodes.append(RiverGraphNode(node_id, "reservoir", name=str(row.get("name", "")), reservoir_id=str(row["reservoir_id"]), metadata={"routing_state": True}))
        source, target = row.get("upstream_node"), row.get("downstream_node")
        if source: edges.append(RiverGraphEdge(f"reservoir_in_{source}_{node_id}", str(source), node_id, "upstream_downstream"))
        if target: edges.append(RiverGraphEdge(f"reservoir_release_{node_id}_{target}", node_id, str(target), "reservoir_release", travel_time=_optional_float(row.get("travel_time"))))
    return RiverGraph(nodes, edges, metadata=result.metadata)


def add_outlet(graph: RiverGraph | Mapping[str, Any], outlet_id: str, upstream_node: str | None = None) -> RiverGraph:
    result = _coerce_graph(graph); nodes, edges = list(result.nodes), list(result.edges)
    nodes.append(RiverGraphNode(str(outlet_id), "outlet", name=str(outlet_id)))
    if upstream_node:
        edges.append(RiverGraphEdge(f"outlet_{upstream_node}_{outlet_id}", str(upstream_node), str(outlet_id)))
    return RiverGraph(nodes, edges, metadata=result.metadata)


def build_subbasin_adjacency(edges: Any, nodes: Any = None) -> tuple[np.ndarray, list[str]]:
    if isinstance(edges, RiverGraph) or isinstance(edges, Mapping):
        graph = _coerce_graph(edges); pairs = _pairs(graph); node_ids = _node_ids(graph)
    else:
        pairs = [(e.source_node, e.target_node) if isinstance(e, RiverGraphEdge) else tuple(e[:2]) for e in edges]
        node_ids = list(nodes or sorted({x for pair in pairs for x in pair}))
    index = {node: i for i, node in enumerate(node_ids)}; matrix = np.zeros((len(node_ids), len(node_ids)), dtype=int)
    for source, target in pairs:
        if source in index and target in index: matrix[index[source], index[target]] = 1
    return matrix, node_ids


def detect_graph_cycles(graph: RiverGraph | Mapping[str, Any]) -> list[list[str]]:
    node_ids = _node_ids(graph); adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in _pairs(graph, include_context=False): adjacency[source].append(target)
    state: dict[str, int] = {node: 0 for node in node_ids}; stack: list[str] = []; cycles: list[list[str]] = []
    def visit(node: str) -> None:
        state[node] = 1; stack.append(node)
        for child in adjacency[node]:
            if state.get(child, 0) == 0: visit(child)
            elif state.get(child) == 1:
                start = stack.index(child); cycle = stack[start:] + [child]
                if cycle not in cycles: cycles.append(cycle)
        stack.pop(); state[node] = 2
    for node in node_ids:
        if state[node] == 0: visit(node)
    return cycles


def detect_cycles(graph: RiverGraph | Mapping[str, Any]) -> list[Any]:
    """Legacy alias returning cycle details."""
    return detect_graph_cycles(graph)


def calculate_topological_order(graph: RiverGraph | Mapping[str, Any]) -> list[str]:
    node_ids = _node_ids(graph); indegree = {node: 0 for node in node_ids}; adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in _pairs(graph, include_context=False):
        if source in indegree and target in indegree: indegree[target] += 1; adjacency[source].append(target)
    queue = deque(sorted(node for node, count in indegree.items() if count == 0)); order = []
    while queue:
        node = queue.popleft(); order.append(node)
        for child in sorted(adjacency[node]):
            indegree[child] -= 1
            if indegree[child] == 0: queue.append(child)
    if len(order) != len(node_ids):
        raise ValueError(f"invalid_hydrologic_cycle: {detect_graph_cycles(graph)}")
    return order


def calculate_upstream_nodes(graph: RiverGraph | Mapping[str, Any], node_id: str) -> list[str]:
    parents: dict[str, list[str]] = defaultdict(list)
    for source, target in _pairs(graph, include_context=False): parents[target].append(source)
    found: set[str] = set(); queue = deque(parents[str(node_id)])
    while queue:
        current = queue.popleft()
        if current not in found: found.add(current); queue.extend(parents[current])
    return [node for node in calculate_topological_order(graph) if node in found]


def calculate_downstream_nodes(graph: RiverGraph | Mapping[str, Any], node_id: str) -> list[str]:
    children: dict[str, list[str]] = defaultdict(list)
    for source, target in _pairs(graph, include_context=False): children[source].append(target)
    found: set[str] = set(); queue = deque(children[str(node_id)])
    while queue:
        current = queue.popleft()
        if current not in found: found.add(current); queue.extend(children[current])
    return [node for node in calculate_topological_order(graph) if node in found]


def calculate_upstream_contributors(graph: RiverGraph | Mapping[str, Any]) -> dict[str, list[str]]:
    return {node: calculate_upstream_nodes(graph, node) for node in _node_ids(graph)}


def calculate_upstream_area(graph: RiverGraph | Mapping[str, Any]) -> dict[str, float]:
    value = _coerce_graph(graph); local = {node.node_id: float(node.area_km2 or 0.0) if node.node_type == "subbasin" else 0.0 for node in value.nodes}
    return {node.node_id: local[node.node_id] + sum(local[item] for item in calculate_upstream_nodes(value, node.node_id)) for node in value.nodes}


def calculate_graph_depth(graph: RiverGraph | Mapping[str, Any]) -> dict[str, int]:
    parents: dict[str, list[str]] = defaultdict(list); depths: dict[str, int] = {}
    for source, target in _pairs(graph, include_context=False): parents[target].append(source)
    for node in calculate_topological_order(graph): depths[node] = 0 if not parents[node] else 1 + max(depths[parent] for parent in parents[node])
    return depths


def calculate_distance_to_outlet(graph: RiverGraph | Mapping[str, Any]) -> dict[str, float]:
    value = _coerce_graph(graph); children: dict[str, list[RiverGraphEdge]] = defaultdict(list)
    for edge in value.edges:
        if edge.edge_type != "station_context": children[edge.source_node].append(edge)
    distance: dict[str, float] = {}
    for node in reversed(calculate_topological_order(value)):
        if not children[node]: distance[node] = 0.0
        else: distance[node] = min(float(edge.distance_km or 1.0) + distance[edge.target_node] for edge in children[node])
    return distance


def validate_river_graph(graph: RiverGraph | Mapping[str, Any]) -> RiverGraphValidationResult:
    value = _coerce_graph(graph); node_ids = [node.node_id for node in value.nodes]; edge_ids = [edge.edge_id for edge in value.edges]
    errors: list[str] = []; warnings: list[str] = []
    if len(node_ids) != len(set(node_ids)): errors.append("node_ids_not_unique")
    if len(edge_ids) != len(set(edge_ids)): errors.append("edge_ids_not_unique")
    missing = sorted({item for edge in value.edges for item in (edge.source_node, edge.target_node) if item not in set(node_ids)})
    if missing: errors.append(f"edge_node_missing:{','.join(missing)}")
    cycles = detect_graph_cycles(value)
    if cycles: errors.append("invalid_hydrologic_cycle")
    outlets = [node.node_id for node in value.nodes if node.node_type == "outlet"]
    if not outlets: errors.append("outlet_missing")
    order = [] if cycles or missing else calculate_topological_order(value)
    required = [node.node_id for node in value.nodes if node.node_type in {"subbasin", "reach", "reservoir"} or node.metadata.get("required")]
    disconnected = [node for node in required if not any(outlet == node or outlet in calculate_downstream_nodes(value, node) for outlet in outlets)] if order else required
    if disconnected: errors.append("disconnected_required_nodes")
    optional_stations = [node.node_id for node in value.nodes if node.node_type in {"monitoring_station", "water_quality_station"} and node.node_id not in required and not any(outlet in calculate_downstream_nodes(value, node.node_id) for outlet in outlets)] if order else []
    if optional_stations: warnings.append(f"disconnected_optional_station:{','.join(optional_stations)}")
    areas = calculate_upstream_area(value) if order else {}; area_errors = []
    for node in value.nodes:
        if node.upstream_area_km2 is not None and abs(float(node.upstream_area_km2) - areas.get(node.node_id, 0.0)) > 1e-6: area_errors.append(node.node_id)
    if area_errors: errors.append(f"upstream_area_inconsistent:{','.join(area_errors)}")
    return RiverGraphValidationResult("passed" if not errors else "failed", errors, warnings, cycles, order, disconnected, outlets, "passed" if not area_errors else "failed")


def validate_directed_acyclic_graph(graph: RiverGraph | Mapping[str, Any]) -> dict[str, Any]:
    cycles = detect_graph_cycles(graph)
    return {"status": "passed" if not cycles else "failed", "cycles": cycles}


def write_graph_manifest(graph: RiverGraph | Mapping[str, Any], output_dir: str | Path = "output/method_inspiration/graph_trend/graph") -> dict[str, Any]:
    value = _coerce_graph(graph); root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    nodes = pd.DataFrame([asdict(node) for node in value.nodes]); edges = pd.DataFrame([asdict(edge) for edge in value.edges]); validation = validate_river_graph(value)
    nodes.to_csv(root / "nodes.csv", index=False); edges.to_csv(root / "edges.csv", index=False)
    order = validation.topological_order; pd.DataFrame({"position": range(len(order)), "node_id": order}).to_csv(root / "topology_order.csv", index=False)
    adjacency, node_ids = build_subbasin_adjacency(value); np.savez(root / "adjacency_matrix.npz", adjacency=adjacency, node_ids=np.asarray(node_ids))
    payload = {"node_count": len(value.nodes), "edge_count": len(value.edges), "directed": True, "direction": "upstream_to_downstream", "is_dag": not validation.cycles, "cycle_count": len(validation.cycles), "topological_order": order, "upstream_area": calculate_upstream_area(value) if order else {}, "graph_depth": calculate_graph_depth(value) if order else {}, "distance_to_outlet_km": calculate_distance_to_outlet(value) if order else {}, "validation_status": validation.status, "metadata": value.metadata}
    (root / "graph_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (root / "graph_validation.json").write_text(json.dumps(validation.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": validation.status, **payload, "output_dir": str(root)}


def _optional_float(value: Any) -> float | None:
    return None if value is None or pd.isna(value) or value == "" else float(value)


def _optional_str(value: Any) -> str | None:
    return None if value is None or pd.isna(value) or value == "" else str(value)
