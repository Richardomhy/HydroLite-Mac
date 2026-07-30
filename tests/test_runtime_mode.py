def test_runtime_modes_block_local_tasks_in_cloud(monkeypatch):
    from hydrolite.runtime_mode import detect_runtime_mode, validate_task_for_mode
    cloud = detect_runtime_mode("cloud_streamlit")
    assert validate_task_for_mode({"local_only":True}, cloud)["status"] == "blocked"
    assert detect_runtime_mode("read_only")["capabilities"]["write_files"] is False
