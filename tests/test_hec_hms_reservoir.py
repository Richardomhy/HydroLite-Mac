from pathlib import Path
from hydrolite.reservoir_routing import build_hms_reservoir_project, run_hms_reservoir_compute_probe
ROOT=Path(__file__).resolve().parents[1]
def test_hms_reservoir_generator_is_original(tmp_path):
    result=build_hms_reservoir_project(ROOT/'data_demo/reservoir/demo_reservoir_config.yaml',tmp_path)
    assert result['report'].exists()
    assert run_hms_reservoir_compute_probe(tmp_path)['status']=='skipped_gate_failed'
