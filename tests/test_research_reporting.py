import json
import subprocess
import sys
from pathlib import Path

import pytest

from hydrolite.research_reporting import write_research_reports


ROOT = Path(__file__).resolve().parents[1]


def test_reporting_writes_metadata_only_registry_bundle(tmp_path):
    paths = write_research_reports(tmp_path)
    expected = {"sources", "methods", "licenses", "integration_matrix", "registry_json", "validation_json", "report_zh", "report_en"}
    assert expected <= set(paths)
    assert all(path.exists() for path in paths.values())
    registry = json.loads(paths["registry_json"].read_text(encoding="utf-8"))
    assert len(registry["sources"]) == 5
    assert "精确复现" in registry["notice"]
    assert "paper_full_text" not in paths["report_zh"].read_text(encoding="utf-8")


def test_research_cli_status_and_method_lookup():
    for args in (("status",), ("source", "gamma_lag_hydrologic_prior_source"), ("method", "gamma_lag_hydrologic_prior")):
        completed = subprocess.run([sys.executable, "-m", "hydrolite", "research", *args], cwd=ROOT, text=True, capture_output=True, check=False)
        assert completed.returncode == 0, completed.stderr


def test_reporting_refuses_protected_raw_data_directory():
    with pytest.raises(ValueError, match="Protected path"):
        write_research_reports(ROOT / "data_raw")
