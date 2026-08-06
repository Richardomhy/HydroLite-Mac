from hydrolite.method_inspiration import build_method_inspiration_report


def test_method_report_writes_clean_room_notice(tmp_path):
    assert build_method_inspiration_report(tmp_path)["report_zh"].exists()
