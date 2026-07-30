from concurrent.futures import ThreadPoolExecutor

from tests.runtime_helpers import configure_runtime


def test_runtime_database_crud_and_concurrency(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.runtime_db import create_project_record, get_database_version, get_project_record, initialize_runtime_database
    assert initialize_runtime_database().exists()
    assert get_database_version() == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda i: create_project_record(project_id=f"p{i}", name=f"P{i}", workspace_path=str(tmp_path / f"p{i}"), status="draft"), range(2)))
    assert get_project_record("p1")["name"] == "P1"


def test_corrupt_database_has_clear_error(monkeypatch, tmp_path):
    root = configure_runtime(monkeypatch, tmp_path); root.mkdir()
    (root / "hydrolite_runtime.sqlite3").write_text("broken")
    from hydrolite.runtime_db import initialize_runtime_database
    try: initialize_runtime_database()
    except RuntimeError as exc: assert "corrupt" in str(exc).lower() or "unavailable" in str(exc).lower()
    else: raise AssertionError("corrupt database accepted")
