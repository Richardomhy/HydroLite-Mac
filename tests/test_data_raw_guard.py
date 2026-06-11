from pathlib import Path

from hydrolite.runner import run_case


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_demo_run_does_not_modify_data_raw():
    before = _snapshot_data_raw()
    run_case(Path("cases/demo.yaml"))
    after = _snapshot_data_raw()
    assert after == before
