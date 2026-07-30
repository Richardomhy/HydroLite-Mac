from hydrolite.desktop.desktop_health import check_desktop_health
from hydrolite.desktop.port_manager import find_free_loopback_port


def test_closed_port_is_unhealthy():
    result = check_desktop_health(find_free_loopback_port())
    assert result["status"] == "failed"
    assert result["url"].startswith("http://127.0.0.1:")
