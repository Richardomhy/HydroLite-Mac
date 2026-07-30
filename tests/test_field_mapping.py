import pandas as pd


def test_chinese_and_english_field_mapping():
    from hydrolite.field_mapping import infer_field_mapping, validate_field_mapping

    result = infer_field_mapping(pd.DataFrame({"时间": ["2026-01-01"], "降雨量": [1]}), "rainfall_observed")
    assert result["mapping"]["时间"] == "timestamp"
    assert result["mapping"]["降雨量"] == "rainfall_mm"
    assert validate_field_mapping(result["mapping"], "rainfall_observed")["status"] == "passed"


def test_low_confidence_requires_mapping():
    from hydrolite.field_mapping import infer_field_mapping

    result = infer_field_mapping(pd.DataFrame({"whenish": [1], "wetness": [2]}), "rainfall_observed")
    assert result["status"] == "needs_mapping"
