from pathlib import Path


def test_manifest_uses_canonical_paths_with_spaces(tmp_path):
    from hydrolite.desktop.backend import write_backend_manifest

    runtime = tmp_path / "HydroLite Runtime With Spaces"
    runtime.mkdir()
    alias = tmp_path / "runtime alias"
    alias.symlink_to(runtime, target_is_directory=True)
    support = tmp_path / "Application Support" / "HydroLite Studio"
    manifest = write_backend_manifest(support / "backend_manifest.json", 1234, 49200, alias / "runtime")
    assert Path(manifest["runtime_dir"]) == (runtime / "runtime").resolve()
    assert Path(manifest["entrypoint"]).name == "streamlit_app.py"
    assert manifest["url"] == "http://127.0.0.1:49200"
    assert (support / "backend_manifest.json").is_file()


def test_desktop_verify_checks_fresh_manifest_and_backend_parent():
    root = Path(__file__).resolve().parents[1]
    script = (root / "script/build_and_run.sh").read_text(encoding="utf-8")
    swift = (root / "desktop/macos/HydroLiteStudio/Sources/BackendManager.swift").read_text(encoding="utf-8")
    assert "VERIFY_STARTED_AT" in script and "stat -f %m" in script
    assert 'ps -o ppid=' in script and "grep -q '^ok$'" in script
    assert "manifest.pid == process?.processIdentifier" in swift
    assert "url.port == manifest.port" in swift
