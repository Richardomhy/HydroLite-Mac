from tests.runtime_helpers import configure_runtime


def test_runtime_paths_are_isolated_and_safe(monkeypatch, tmp_path):
    root = configure_runtime(monkeypatch, tmp_path)
    from hydrolite.runtime_paths import ensure_runtime_directories, sanitize_runtime_identifier, validate_runtime_path
    paths = ensure_runtime_directories("run_1", "task_1")
    assert paths["root"] == root.resolve()
    assert sanitize_runtime_identifier("Demo 项目") == "Demo"
    try: validate_runtime_path(tmp_path.parent)
    except ValueError: pass
    else: raise AssertionError("path escape accepted")
