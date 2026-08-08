def test_connectors_degrade_without_credentials_and_do_not_download():
    from hydrolite.connectors import get_connector, list_connectors

    rows = list_connectors()
    assert {row["connector_id"] for row in rows} == {"local", "gee", "earthdata", "cds", "stac"}
    assert all(row["download_execute_default"] is False for row in rows)
    assert get_connector("earthdata").download({}, execute=False)["status"] == "dry_run"
    assert get_connector("cds").detect_authentication().get("credentials_redacted") is True
    assert "seasonal_forecast" in get_connector("cds").list_supported_datasets()
    assert {"GRACE", "GRACE-FO"} <= set(get_connector("earthdata").list_supported_datasets())
    gee = get_connector("gee").healthcheck()
    assert "gee_compute_authentication" in gee
    assert "gee_catalog_metadata_transport" in gee


def test_connector_bbox_date_and_stac_whitelist_gates():
    from hydrolite.connectors import get_connector

    for connector_id in ("gee", "earthdata", "cds", "stac"):
        try:
            get_connector(connector_id).search({})
        except ValueError:
            pass
        else:
            raise AssertionError(f"{connector_id} accepted an unbounded request")


def test_data_center_streamlit_pages_import():
    from hydrolite.ui.pages import data_center, data_connectors

    assert callable(data_center.render)
    assert callable(data_connectors.render)
