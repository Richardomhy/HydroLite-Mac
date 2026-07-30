from pathlib import Path
from hydrolite.reservoir_routing import build_hms_413_reservoir_project,evaluate_hms_413_reservoir_compute_gate
ROOT=Path(__file__).resolve().parents[1]
def test_verified_project_is_gated_without_inflow(tmp_path):
    build_hms_413_reservoir_project(ROOT/'data_demo/reservoir/demo_reservoir_config.yaml',tmp_path);assert evaluate_hms_413_reservoir_compute_gate(tmp_path)['status']=='gate_failed'
