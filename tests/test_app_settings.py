from tests.runtime_helpers import configure_runtime


def test_settings_safe_defaults_and_validation(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.app_settings import load_settings, save_settings, validate_settings
    settings = load_settings(); settings["password"] = "do-not-save"
    path = save_settings(settings)
    assert "do-not-save" not in path.read_text()
    assert validate_settings(load_settings())["status"] == "passed"
