from hydrolite.gee_catalog.compare import compare_datasets


def test_compare_is_bounded_and_explains_differences():
    result = compare_datasets(["UCSB-CHG/CHIRPS/DAILY", "USGS/SRTMGL1_003"])
    assert result["status"] == "passed"
    assert {"bands", "license", "hydrolite_suitability"} <= set(result["differences"])
