import json
from urllib.error import HTTPError

from hydrolite.gee_catalog import transport
from hydrolite.gee_catalog.transport import GeeCatalogTransportResult, classify_transport_error, fetch_catalog_object


def _result(transport_id, status="success", error_type=None):
    return GeeCatalogTransportResult(transport_id, status, "gs://earthengine-stac/catalog/catalog.json", authentication_mode="anonymous", error_type=error_type)


def test_transport_failover_and_invalid_json(monkeypatch):
    payload = json.dumps({"type": "Catalog", "links": []}).encode()
    def fake_read(uri, transport_id):
        if transport_id == "google_cloud_storage_anonymous":
            return None, _result(transport_id, "failed", "anonymous_access_denied")
        return payload, _result(transport_id)
    monkeypatch.setattr(transport, "read_gs_uri", fake_read)
    root, selected, attempts = fetch_catalog_object("gs://earthengine-stac/catalog/catalog.json", transport_priority=["google_cloud_storage_anonymous", "google_cloud_storage_authenticated"])
    assert root["type"] == "Catalog"
    assert selected.transport_id == "google_cloud_storage_authenticated"
    assert len(attempts) == 2

    monkeypatch.setattr(transport, "read_gs_uri", lambda uri, transport_id: (b"{", _result(transport_id)))
    root, selected, _ = fetch_catalog_object("gs://earthengine-stac/catalog/catalog.json", transport_priority=["google_cloud_storage_anonymous"])
    assert root is None
    assert selected.error_type == "invalid_stac"


def test_transport_error_classification():
    assert classify_transport_error(HTTPError("https://x", 404, "not found", None, None)) == "official_object_not_found"
    assert classify_transport_error(TimeoutError("timed out")) == "network_timeout"
    assert classify_transport_error(ModuleNotFoundError("google.cloud.storage")) == "transport_dependency_missing"


def test_gcloud_and_gsutil_adapters_use_subprocess_result(monkeypatch):
    monkeypatch.setattr(transport, "_read_subprocess", lambda command, transport_id, uri, authentication_mode: (b"{}", _result(transport_id)))
    assert transport.read_with_gcloud("gs://earthengine-stac/catalog/catalog.json")[1].transport_id == "gcloud_storage"
    assert transport.read_with_gsutil("gs://earthengine-stac/catalog/catalog.json")[1].transport_id == "gsutil"
