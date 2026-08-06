from hydrolite.graph_hydrology_features import aggregate_upstream_features


def test_upstream_features_follow_directed_edges():
    rows=[{"timestamp":"t","node_id":"A","surface_runoff":1},{"timestamp":"t","node_id":"B","surface_runoff":2}]
    assert aggregate_upstream_features(rows,{"nodes":["A","B"],"edges":[("A","B")]}).query("node_id == 'B'").surface_runoff.iloc[0] == 3
