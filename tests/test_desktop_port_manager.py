import pytest

from hydrolite.desktop.port_manager import find_free_loopback_port, reject_non_loopback_address, validate_loopback_url


def test_dynamic_loopback_port_and_rejection():
    port = find_free_loopback_port()
    assert 0 < port < 65536
    assert validate_loopback_url(f"http://127.0.0.1:{port}")
    with pytest.raises(ValueError):
        reject_non_loopback_address("0.0.0.0")
