import json
import os

from hydrolite.desktop.single_instance import acquire_application_lock, inspect_existing_instance, recover_stale_lock, release_application_lock


def test_single_instance_and_stale_lock(tmp_path):
    lock = tmp_path / "instance.lock"
    assert acquire_application_lock(lock)["status"] == "acquired"
    assert acquire_application_lock(lock)["status"] == "already_running"
    assert release_application_lock(lock)["status"] == "released"
    lock.write_text(json.dumps({"pid": 99999999, "process_started": "old"}), encoding="utf-8")
    assert inspect_existing_instance(lock)["status"] == "stale"
    assert recover_stale_lock(lock)["status"] == "recovered"
