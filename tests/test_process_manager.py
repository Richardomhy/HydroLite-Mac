import sys


def test_process_manager_stops_only_managed_process(tmp_path):
    from hydrolite.process_manager import start_managed_process, terminate_process_tree, verify_process_stopped
    pid = start_managed_process([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, {}, tmp_path/"out", tmp_path/"err")
    assert terminate_process_tree(pid)
    assert verify_process_stopped(pid)
    assert terminate_process_tree(999999) is False
