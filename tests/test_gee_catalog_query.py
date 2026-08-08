from hydrolite.gee_catalog import search_catalog


def test_offline_catalog_search_and_relaxed_status():
    assert search_catalog("precipitation")["matches"]
    result = search_catalog("not-a-dataset")
    assert result["status"] == "no_exact_match"
    assert "relaxed_alternatives" in result


def test_chinese_alias_and_hard_filters():
    assert search_catalog("降雨")["matches"]
    assert search_catalog("precipitation", maximum_nominal_resolution_m=100)["status"] == "no_exact_match"
    assert search_catalog("precipitation", maximum_matched_band_resolution_m=100000)["matches"]
