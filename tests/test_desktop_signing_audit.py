from hydrolite.desktop.signing_audit import audit_macos_signature, detect_developer_identities


def test_missing_app_and_identity_detection(tmp_path):
    result = audit_macos_signature(tmp_path / "missing.app")
    assert result["status"] == "failed"
    assert isinstance(detect_developer_identities(), list)
    assert result["get_task_allow"] is False
