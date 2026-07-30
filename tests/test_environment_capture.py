from tests.runtime_helpers import configure_runtime


def test_environment_capture_redacts_connector_credentials(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.environment_capture import capture_environment, write_environment_snapshot
    result = capture_environment(tmp_path)
    text = str(result).lower()
    assert "password=" not in text and "authorization" not in text
    assert isinstance(result["pip_packages"], list)
    assert write_environment_snapshot(tmp_path/"snapshot", result)["json"].exists()
