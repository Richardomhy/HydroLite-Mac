from hydrolite.river_graph import calculate_topological_order, detect_cycles, validate_directed_acyclic_graph


def test_river_graph_direction_and_cycle_gate():
    graph={"nodes":["A","B","C"],"edges":[("A","B"),("B","C")]}
    assert calculate_topological_order(graph)==["A","B","C"] and not detect_cycles(graph) and validate_directed_acyclic_graph(graph)["status"]=="passed"
