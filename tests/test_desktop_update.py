import json
import pytest

from hydrolite.desktop.desktop_update import inspect_update_status, parse_appcast, validate_update_url


def test_update_fallback_and_https_gate(tmp_path):
    config = tmp_path / "update.json"
    config.write_text(json.dumps({"enabled": False, "feed_url": ""}), encoding="utf-8")
    assert inspect_update_status(config)["update_readiness"] == "framework_ready_configuration_missing"
    with pytest.raises(ValueError):
        validate_update_url("http://example.com/appcast.xml")


def test_example_appcast_parses():
    assert parse_appcast("packaging/macos/appcast.example.xml") == []


def test_integrated_feed_waits_for_public_key():
    status = inspect_update_status("packaging/macos/update_config.example.json")
    assert status["sparkle_integrated"] is True
    assert status["feed_configured"] is True
    assert status["update_readiness"] == "framework_integrated_signing_key_missing"
