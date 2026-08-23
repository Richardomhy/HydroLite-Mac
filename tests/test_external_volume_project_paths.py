from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from hydrolite.water_environment import run_water_environment_source_accounting, water_environment_status


ROOT = Path(__file__).resolve().parents[1]


def _tree_hash(root: Path) -> str:
    digest = sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_external_storage_unavailable_does_not_create_old_path(tmp_path):
    missing = tmp_path / "external volume with spaces" / "missing"
    with pytest.raises(FileNotFoundError, match="external_project_storage_unavailable"):
        run_water_environment_source_accounting(missing, workspace_dir=tmp_path / "workspace", output_dir=tmp_path / "output")
    assert not missing.exists()


def test_business_code_has_no_hard_coded_repository_path():
    for name in ("water_environment.py", "pollution_source_inventory.py", "source_load_ledger.py"):
        text = (ROOT / "hydrolite" / name).read_text(encoding="utf-8")
        assert "/Users/minghenyu/Documents/hydrolite 模型" not in text
        assert "/Volumes/ycz - Data/HydroLite-Mac" not in text


def test_data_raw_and_emergency_tree_are_untouched_by_status(tmp_path):
    data_before = _tree_hash(ROOT / "data_raw")
    emergency_before = _tree_hash(ROOT / "tmp_emergency_0722")
    water_environment_status(tmp_path)
    assert _tree_hash(ROOT / "data_raw") == data_before
    assert _tree_hash(ROOT / "tmp_emergency_0722") == emergency_before
