import pytest

from hydrolite.gee_catalog.transport import resolve_stac_link


def test_resolves_gs_https_and_relative_catalog_links():
    parent = "gs://earthengine-stac/catalog/catalog.json"
    assert resolve_stac_link(parent, "gs://earthengine-stac/catalog/AAFC/catalog.json").endswith("AAFC/catalog.json")
    assert resolve_stac_link(parent, "https://storage.googleapis.com/earthengine-stac/catalog/AAFC/catalog.json").endswith("AAFC/catalog.json")
    assert resolve_stac_link(parent, "AAFC/catalog.json") == "gs://earthengine-stac/catalog/AAFC/catalog.json"


@pytest.mark.parametrize("href", ["file:///tmp/x.json", "ftp://example.com/x", "https://example.com/x", "../secret.json", "http://localhost/x"])
def test_rejects_unsafe_catalog_links(href):
    with pytest.raises(ValueError):
        resolve_stac_link("gs://earthengine-stac/catalog/catalog.json", href)
