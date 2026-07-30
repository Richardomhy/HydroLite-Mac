from hydrolite.desktop import crash_recovery, desktop_paths


def test_abnormal_shutdown_marker_and_recovery(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop_paths, "get_application_support_dir", lambda: tmp_path)
    monkeypatch.setattr(crash_recovery, "get_application_support_dir", lambda: tmp_path)
    crash_recovery.record_desktop_start()
    assert crash_recovery.detect_unclean_shutdown()
    crash_recovery.record_clean_shutdown()
    assert not crash_recovery.detect_unclean_shutdown()
