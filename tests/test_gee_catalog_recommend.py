from hydrolite.gee_catalog.recommend import recommend_datasets


def test_recommendation_is_transparent_and_not_unique():
    result = recommend_datasets("continuous_hydrology")
    assert result["status"] == "passed"
    assert all("score_components" in row and "limitations" in row for row in result["recommendations"])
    assert recommend_datasets("no_such_model")["status"] == "unknown_use_case"
