from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_clean_room_policy_blocks_unlicensed_skill_reuse():
    config = yaml.safe_load((ROOT / "config" / "research_sources.yaml").read_text(encoding="utf-8"))
    policy = config["policy"]
    skill = config["third_party_sources"][0]
    assert policy["clean_room_required"] is True
    assert skill["license_status"] == "license_file_missing"
    assert skill["integration_mode"] == "method_inspired_clean_room"
    assert skill["copy_allowed"] is False
    assert skill["runtime_dependency_allowed"] is False
    assert "ruiduobao/gee-dataset-intelligence-skill" in policy["prohibited_runtime_dependencies"]
