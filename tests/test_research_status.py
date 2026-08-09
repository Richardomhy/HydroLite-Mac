from hydrolite.provenance import build_provenance_record, experiment_output_path, is_protected_path
from hydrolite.research_status import ExperimentStatus, MethodStatus, is_experiment_status, is_method_status
from hydrolite.capability_registry import get_capability


def test_shared_statuses_are_explicit_and_validated():
    assert ExperimentStatus.PARTIAL.value == "partial"
    assert MethodStatus.METHOD_INSPIRED_CLEAN_ROOM.value == "method_inspired_clean_room"
    assert is_experiment_status("planned")
    assert not is_experiment_status("production_ready")
    assert is_method_status("source_incomplete")
    assert not is_method_status("copy_paper_code")
    assert get_capability("research_method_registry")["status"] == "partial"


def test_provenance_keeps_outputs_away_from_protected_paths():
    output = experiment_output_path("method_inspiration")
    assert output.name == "method_inspiration"
    assert not is_protected_path(output)
    assert is_protected_path("data_raw")
    record = build_provenance_record(["example"], synthetic_demo=True)
    assert record["physical_water_balance_authoritative"] is True
