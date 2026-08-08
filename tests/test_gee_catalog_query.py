from hydrolite.gee_catalog import search_catalog
from hydrolite.gee_catalog.loader import fixture_records


def test_offline_catalog_search_and_relaxed_status():
    assert search_catalog("precipitation")["matches"]
    result = search_catalog("not-a-dataset")
    assert result["status"] == "no_exact_match"
    assert "relaxed_alternatives" in result


def test_chinese_alias_and_hard_filters():
    records = fixture_records()
    assert search_catalog("降雨", records=records)["matches"]
    assert search_catalog("precipitation", records=records, maximum_nominal_resolution_m=100)["status"] == "no_exact_match"
    assert search_catalog("precipitation", records=records, maximum_matched_band_resolution_m=100000)["matches"]
