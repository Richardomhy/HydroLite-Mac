import socket


def test_diagnostic_classifies_addresses_and_redacts_proxy_credentials(monkeypatch):
    from hydrolite.connectors.diagnostics import diagnose_url

    monkeypatch.setenv("HTTPS_PROXY", "https://alice:topsecret@proxy.example.test:8443/path?token=hide")
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd00::12", 443, 0, 0)),
    ])
    result = diagnose_url("https://data.example.test/catalog", ["data.example.test"], probe=False)
    assert result["status"] == "non_public_resolution"
    assert {row["classification"] for row in result["resolved_addresses"]} == {"public", "private"}
    assert result["proxy_environment"]["HTTPS_PROXY"] == {"status": "present", "hosts": ["proxy.example.test"]}
    assert result["proxy_environment"]["NO_PROXY"]["status"] == "present"
    encoded = str(result)
    assert "topsecret" not in encoded and "token=hide" not in encoded


def test_diagnostic_handles_dns_failure_without_credentials(monkeypatch):
    from hydrolite.connectors.diagnostics import diagnose_url

    def fail(*args, **kwargs):
        raise socket.gaierror("secret resolver detail")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    result = diagnose_url("https://data.example.test/", ["data.example.test"], probe=False)
    assert result["status"] == "dns_failure"
    assert result["resolved_addresses"] == []
    assert "secret resolver detail" not in str(result)


def test_cache_reports_unavailable_read_only_and_insufficient_storage(tmp_path, monkeypatch):
    import shutil
    import hydrolite.dataset_cache as cache_module
    from hydrolite.dataset_cache import DatasetCache

    available = DatasetCache(tmp_path / "external cache", max_bytes=1024)
    assert available.inspect_storage()["status"] == "available"
    monkeypatch.setattr(cache_module.os, "access", lambda *_args: False)
    assert available.inspect_storage()["status"] == "data_cache_read_only"
    monkeypatch.setattr(cache_module.os, "access", lambda *_args: True)
    monkeypatch.setattr(cache_module.shutil, "disk_usage", lambda *_args: shutil._ntuple_diskusage(1, 1, 1))
    assert available.inspect_storage()["status"] == "data_cache_insufficient_space"


def test_unmounted_external_cache_does_not_fall_back(tmp_path, monkeypatch):
    import hydrolite.dataset_cache as cache_module
    from hydrolite.connectors.transport import ConnectorError
    from hydrolite.dataset_cache import DatasetCache

    monkeypatch.setattr(cache_module.Path, "is_mount", lambda _self: False)
    try:
        DatasetCache("/Volumes/hydrolite-not-mounted/cache")
    except ConnectorError as exc:
        assert exc.status == "data_cache_storage_unavailable"
    else:
        raise AssertionError("unmounted external storage must not fall back")
