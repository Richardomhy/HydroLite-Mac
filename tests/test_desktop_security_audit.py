from hydrolite.desktop.security_audit import audit_desktop_bundle


def test_security_audit_blocks_forbidden_content(tmp_path):
    safe = tmp_path / "Safe.app"
    safe.mkdir()
    assert audit_desktop_bundle(safe)["status"] == "passed"
    forbidden = safe / "data_raw"
    forbidden.mkdir()
    assert audit_desktop_bundle(safe)["status"] == "failed"
