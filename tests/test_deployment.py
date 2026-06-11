from pathlib import Path
import importlib


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_streamlit_app_imports():
    module = importlib.import_module("streamlit_app")
    assert callable(module.main)


def test_ui_app_has_main():
    import hydrolite.ui.app as app

    assert callable(app.main)


def test_app_helpers_work_without_external_swmm_python(monkeypatch):
    from hydrolite.ui.app import is_streamlit_cloud, scan_case_files, swmm_python_status

    monkeypatch.delenv("HYDROLITE_SWMM_PYTHON", raising=False)
    monkeypatch.delenv("STREAMLIT_CLOUD", raising=False)
    exists, path = swmm_python_status()
    assert exists is False
    assert path == ""
    assert isinstance(is_streamlit_cloud(), bool)
    assert any(case.name == "demo.yaml" for case in scan_case_files(Path("cases")))


def test_cloud_fallback_does_not_require_external_solver(monkeypatch):
    from hydrolite.swmm.runner import find_external_solver_python

    monkeypatch.delenv("HYDROLITE_SWMM_PYTHON", raising=False)
    result = find_external_solver_python()
    assert result is None or result.exists()


def test_deployment_docs_and_requirements_exist():
    assert Path("docs/deployment.md").exists()
    assert Path("docs/github_push_commands.md").exists()
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    assert "streamlit" in requirements


def test_deployment_checks_do_not_modify_data_raw():
    before = _snapshot_data_raw()
    importlib.import_module("streamlit_app")
    from hydrolite.ui.app import swmm_python_status

    swmm_python_status()
    after = _snapshot_data_raw()
    assert after == before
