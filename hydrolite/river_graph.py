from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import json
import numpy as np
import pandas as pd


def build_graph_from_reaches(reaches):
    frame = pd.DataFrame(reaches); edges = []
    for row in frame.to_dict("records"):
        up, down = row.get("upstream_reach_id"), row.get("downstream_reach_id")
        if up and down: edges.append((str(up), str(down)))
    nodes = sorted(set(frame.get("reach_id", pd.Series(dtype=str)).astype(str)).union({x for edge in edges for x in edge}))
    return {"nodes": nodes, "edges": edges, "node_type": "reach"}


def build_subbasin_adjacency(edges, nodes=None):
    nodes = nodes or sorted({x for edge in edges for x in edge}); index = {node: i for i, node in enumerate(nodes)}; matrix = np.zeros((len(nodes), len(nodes)), dtype=int)
    for upstream, downstream in edges: matrix[index[upstream], index[downstream]] = 1
    return matrix, nodes


def detect_cycles(graph):
    edges = graph["edges"]; adjacency = defaultdict(list)
    for up, down in edges: adjacency[up].append(down)
    visiting, visited, cycles = set(), set(), []
    def visit(node):
        if node in visiting: cycles.append(node); return
        if node in visited: return
        visiting.add(node)
        for child in adjacency[node]: visit(child)
        visiting.remove(node); visited.add(node)
    for node in graph["nodes"]: visit(node)
    return sorted(set(cycles))


def validate_directed_acyclic_graph(graph): return {"status": "passed" if not detect_cycles(graph) else "failed", "cycles": detect_cycles(graph)}

def calculate_topological_order(graph):
    indegree = {node: 0 for node in graph["nodes"]}; adjacency = defaultdict(list)
    for up, down in graph["edges"]: indegree[down] += 1; adjacency[up].append(down)
    queue = deque(sorted(node for node, count in indegree.items() if count == 0)); order = []
    while queue:
        node = queue.popleft(); order.append(node)
        for child in adjacency[node]:
            indegree[child] -= 1
            if indegree[child] == 0: queue.append(child)
    if len(order) != len(graph["nodes"]): raise ValueError("Directed graph contains a cycle")
    return order


def calculate_upstream_contributors(graph):
    parents = defaultdict(list)
    for up, down in graph["edges"]: parents[down].append(up)
    result = {}
    def ancestors(node):
        values = set(parents[node])
        for parent in parents[node]: values.update(ancestors(parent))
        return values
    for node in graph["nodes"]: result[node] = sorted(ancestors(node))
    return result


def write_graph_manifest(graph, output_dir="output/method_inspiration"):
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True); adjacency, nodes = build_subbasin_adjacency(graph["edges"], graph["nodes"])
    pd.DataFrame({"node_id": nodes}).to_csv(root / "graph_nodes.csv", index=False); pd.DataFrame(graph["edges"], columns=["upstream_id", "downstream_id"]).to_csv(root / "graph_edges.csv", index=False); np.savez(root / "adjacency_matrix.npz", adjacency=adjacency, node_ids=np.asarray(nodes))
    payload = {"node_count": len(nodes), "edge_count": len(graph["edges"]), "is_dag": not bool(detect_cycles(graph)), "topological_order": calculate_topological_order(graph), "direction": "upstream_to_downstream"}; (root / "graph_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "passed", **payload}
