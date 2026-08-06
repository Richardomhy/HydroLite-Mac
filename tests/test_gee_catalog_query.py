from hydrolite.gee_catalog import search_catalog


def test_offline_catalog_search_and_relaxed_status():
    assert search_catalog("precipitation")["matches"]
    assert search_catalog("not-a-dataset")["no_exact_match"]
