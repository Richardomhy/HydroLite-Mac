from hydrolite.graph_temporal_model import fit_graph_linear_residual, validate_graph_temporal_mode


def run_graph_temporal_residual(physical_prediction, observed, mode="graph_linear_residual", purpose="hindcast"):
    gate = validate_graph_temporal_mode(mode, purpose)
    return gate if gate["status"] != "passed" else {"status": "passed", "mode": mode, **fit_graph_linear_residual(physical_prediction, observed)}
