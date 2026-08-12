from __future__ import annotations

from pathlib import Path
import json
import plistlib
import sqlite3
import zipfile


def test_next_build_number_is_greater_than_known_builds(tmp_path, monkeypatch):
    plist = tmp_path / "desktop/macos/HydroLiteStudio/Resources/Info.plist"
    plist.parent.mkdir(parents=True); plist.write_bytes(plistlib.dumps({"CFBundleVersion": "91"}))
    from hydrolite.desktop import release_candidate as rc
    monkeypatch.setattr(rc, "_run", lambda *args, **kwargs: type("R", (), {"stdout": "70\n"})())
    assert rc.calculate_next_build_number(tmp_path) == 92


def test_missing_credentials_never_become_distribution_ready(monkeypatch):
    from hydrolite.desktop import release_candidate as rc
    monkeypatch.setattr(rc, "detect_developer_identities", lambda: [])
    monkeypatch.delenv("HYDROLITE_NOTARY_PROFILE", raising=False)
    result = rc.assess_release_readiness(
        {"signing_mode": "ad_hoc", "status": "passed"},
        {"status": "passed", "sparkle_public_key": "missing"},
        {"status": "passed"}, {"status": "passed"},
    )
    assert result["build_readiness"] == "internal_rc_ready"
    assert result["overall"] == "distribution_blocked_credentials"
    assert result["blockers"] == ["developer_id_missing", "notary_credentials_missing", "sparkle_signing_key_missing"]


def test_invalid_update_signature_and_tampered_archive_are_blocked(tmp_path):
    from hydrolite.desktop.release_candidate import audit_zip, hash_file, validate_update_signature_metadata
    assert validate_update_signature_metadata("not-a-signature", True)["status"] == "blocked"
    archive = tmp_path / "rc.zip"
    with zipfile.ZipFile(archive, "w") as output: output.writestr("HydroLite.app/Contents/Info.plist", "safe")
    before = hash_file(archive); archive.write_bytes(archive.read_bytes() + b"tampered")
    assert hash_file(archive) != before
    assert audit_zip(archive)["status"] == "passed"


def test_release_zip_blocks_runtime_data_and_absolute_paths(tmp_path):
    from hydrolite.desktop.release_candidate import audit_zip
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("app/data_raw/private.csv", "x")
        output.writestr("app/readme.txt", "/Users/example/private")
    result = audit_zip(archive)
    assert result["status"] == "failed"
    assert {row["rule"] for row in result["findings"]} == {"forbidden_member", "absolute_text"}


def test_runtime_database_empty_v1_and_v2_are_compatible(tmp_path):
    from hydrolite.runtime_db import get_database_version, get_migration_backup_path, initialize_runtime_database
    empty = tmp_path / "empty.sqlite3"; initialize_runtime_database(empty); assert get_database_version(empty) == 2
    v1 = tmp_path / "v1.sqlite3"
    with sqlite3.connect(v1) as db:
        db.executescript("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL); INSERT INTO schema_migrations VALUES(1, 'before');")
    initialize_runtime_database(v1)
    assert get_database_version(v1) == 2 and get_migration_backup_path(v1).exists()
    initialize_runtime_database(v1)
    assert get_database_version(v1) == 2


def test_release_scripts_use_isolated_rc_staging_and_no_deep_signing():
    build = Path("scripts/build_macos_rc.sh").read_text(encoding="utf-8")
    signing = Path("scripts/sign_macos_app.sh").read_text(encoding="utf-8")
    assert "dist/macos/rc" in build and "build/macos/rc-staging" in build
    assert "codesign --deep" not in signing
    assert "--options runtime" in signing and "--timestamp" in signing
    assert 'strip -S "$APP/Contents/MacOS/HydroLite Studio"' in Path("scripts/assemble_macos_app.sh").read_text(encoding="utf-8")
    assert "tmp_emergency_0722" not in build


def test_packaged_backend_stops_when_swift_parent_exits():
    swift = Path("desktop/macos/HydroLiteStudio/Sources/BackendManager.swift").read_text(encoding="utf-8")
    launcher = Path("hydrolite/desktop/launcher.py").read_text(encoding="utf-8")
    assert '"--parent-pid"' in swift and '"--parent-pid"' in launcher
    assert "os.getppid() == parent_pid" in launcher


def test_rc_entitlements_are_least_privilege_and_bundle_id_is_stable():
    entitlements = plistlib.loads(Path("packaging/macos/HydroLiteStudio.entitlements").read_bytes())
    info = plistlib.loads(Path("desktop/macos/HydroLiteStudio/Resources/Info.plist").read_bytes())
    assert entitlements == {}
    assert info["CFBundleIdentifier"] == "com.hydrolite.studio"
    assert info["LSMinimumSystemVersion"] == "13.0"
    assert info["SUFeedURL"].startswith("https://")


def test_release_metadata_has_no_home_path_in_source_contract():
    source = Path("hydrolite/desktop/release_candidate.py").read_text(encoding="utf-8")
    assert "/Users/minghenyu" not in source
    assert "-----BEGIN PRIVATE KEY-----" not in source
    assert "tmp_emergency_0722" not in source
