from pathlib import Path
import json
import stat
import zipfile

import pytest

from tests.delivery_helpers import make_delivery_workspace


def _unsafe_zip(path: Path, member: str, *, symlink: bool = False) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo(member)
        if symlink: info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"payload")
        archive.writestr("package_manifest.json", json.dumps({"package_schema_version": 1, "project_id": "p", "mode": "thin", "checksums": {}}))
    return path


@pytest.mark.parametrize(("member", "symlink", "error"), [
    ("../escape.txt", False, "path_traversal"),
    ("/absolute.txt", False, "absolute_path"),
    ("link", True, "symlink"),
])
def test_package_verification_blocks_unsafe_members(tmp_path, member, symlink, error):
    from hydrolite.integrity_verification import verify_project_package
    result = verify_project_package(_unsafe_zip(tmp_path / f"unsafe-{error}.zip", member, symlink=symlink))
    assert result["status"] == "failed"
    assert any(error in item for item in result["errors"])


def test_sensitive_scan_blocks_secret_without_printing_value(tmp_path):
    from hydrolite.deliverable_package import scan_deliverable_for_sensitive_content
    secret = tmp_path / "config.txt"; secret.write_text("api_key=sk-not-a-real-secret-123456\n", encoding="utf-8")
    result = scan_deliverable_for_sensitive_content([secret])
    assert result["status"] == "failed"
    serialized = json.dumps(result)
    assert "sk-not-a-real-secret" not in serialized


def test_project_package_rejects_data_raw_selection(monkeypatch, tmp_path):
    workspace = make_delivery_workspace(monkeypatch, tmp_path)
    from hydrolite.project_versioning import create_project_version
    from hydrolite.deliverable_package import create_project_package
    create_project_version(workspace)
    raw = tmp_path / "data_raw" / "private.csv"; raw.parent.mkdir(); raw.write_text("x\n1\n")
    with pytest.raises(ValueError, match="data_raw"):
        create_project_package(workspace, tmp_path / "blocked.zip", mode="portable", selected_data=[raw])
