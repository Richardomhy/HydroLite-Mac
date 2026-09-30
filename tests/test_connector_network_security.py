from urllib.request import Request

import pytest


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.1.2", "::1", "fd00::1", "fe80::1"])
def test_production_policy_blocks_non_public_ipv4_and_ipv6(monkeypatch, address):
    import socket
    from hydrolite.connectors.transport import ConnectorError, validate_public_url

    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    row = (family, socket.SOCK_STREAM, 6, "", (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [row])
    with pytest.raises(ConnectorError) as caught:
        validate_public_url("https://data.example.test/a.csv", ["data.example.test"])
    assert caught.value.status == "non_public_resolution"


def test_production_policy_allows_public_addresses_and_blocks_mixed_dns(monkeypatch):
    import socket
    from hydrolite.connectors.transport import ConnectorError, validate_public_url

    def row(address):
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return (family, socket.SOCK_STREAM, 6, "", (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443))

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [row("1.1.1.1")])
    assert validate_public_url("https://data.example.test/a.csv", ["data.example.test"])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [row("1.1.1.1"), row("fd00::1")])
    with pytest.raises(ConnectorError, match="non-public"):
        validate_public_url("https://data.example.test/a.csv", ["data.example.test"])


def test_test_policy_only_allows_loopback_and_never_changes_production_default(monkeypatch):
    import socket
    from hydrolite.connectors.transport import ConnectorError, NetworkSecurityPolicy, validate_public_url

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 9000))])
    with pytest.raises(ConnectorError):
        validate_public_url("http://127.0.0.1:9000/data.csv", ["127.0.0.1"])
    assert validate_public_url("http://127.0.0.1:9000/data.csv", ["127.0.0.1"], NetworkSecurityPolicy.TEST_LOOPBACK_ALLOWED)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 9000))])
    with pytest.raises(ConnectorError):
        validate_public_url("http://data.example.test:9000/data.csv", ["data.example.test"], NetworkSecurityPolicy.TEST_LOOPBACK_ALLOWED)


def test_public_redirect_to_private_target_is_revalidated(monkeypatch):
    import socket
    from hydrolite.connectors.transport import ConnectorError, PublicRedirect

    def addresses(host, port, **kwargs):
        ip = "1.1.1.1" if host == "public.example.test" else "192.168.1.2"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", addresses)
    handler = PublicRedirect(["public.example.test", "private.example.test"])
    request = Request("https://public.example.test/start")
    with pytest.raises(ConnectorError) as caught:
        handler.redirect_request(request, None, 302, "Found", {}, "https://private.example.test/secret")
    assert caught.value.status == "non_public_resolution"
