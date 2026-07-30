import pandas as pd


def test_time_parsing_duplicates_missing_and_irregular():
    from hydrolite.timeseries_ingestion import detect_duplicate_timestamps, detect_missing_timestamps, infer_time_interval, parse_timestamp_column

    frame = pd.DataFrame({"时间": ["2026年1月1日 00:00", "2026年1月1日 01:00", "2026年1月1日 03:00"], "rainfall_mm": [0, 1, 2]})
    parsed = parse_timestamp_column(frame, "时间")
    assert parsed["时间"].notna().all()
    assert infer_time_interval(parsed, "时间")["status"] == "irregular"
    assert detect_missing_timestamps(parsed, "时间")
    duplicated = pd.concat([parsed, parsed.iloc[[0]]])
    assert detect_duplicate_timestamps(duplicated, "时间")
