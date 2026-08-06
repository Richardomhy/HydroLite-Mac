from hydrolite.river_graph import build_subbasin_adjacency


def build_water_quality_graph(edges, stations):
    matrix, nodes = build_subbasin_adjacency(edges, stations)
    return {"nodes": nodes, "adjacency": matrix, "direction": "upstream_to_downstream"}
