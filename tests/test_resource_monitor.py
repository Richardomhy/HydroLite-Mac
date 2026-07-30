def test_resource_checks(tmp_path):
    from hydrolite.resource_monitor import inspect_cpu, inspect_disk_space, inspect_memory, validate_resource_requirements
    assert inspect_disk_space(tmp_path)["writable"]
    assert inspect_cpu()["logical_cpu_count"]
    assert "total_bytes" in inspect_memory()
    assert validate_resource_requirements({"run_dir":str(tmp_path),"tasks":[]})["status"] == "passed"
