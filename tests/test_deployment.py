from tests.runtime_helpers import configure_runtime


def test_deployment_and_streamlit_pages(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.deployment import diagnose_local_deployment, diagnose_streamlit_cloud_deployment
    from hydrolite.ui.pages import artifact_center, project_center, run_center, system_center, task_center
    assert diagnose_local_deployment()["status"] == "passed"
    assert diagnose_streamlit_cloud_deployment()["status"] == "passed"
    assert all(callable(page.render) for page in (project_center, run_center, task_center, artifact_center, system_center))


def test_stop_script_refuses_unrelated_process(monkeypatch, tmp_path):
    import subprocess, sys
    runtime = configure_runtime(monkeypatch, tmp_path)
    (runtime/"locks").mkdir(parents=True)
    process = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    try:
        (runtime/"locks"/"streamlit.pid").write_text(str(process.pid))
        result = subprocess.run(["bash","scripts/stop_hydrolite_local.sh"], capture_output=True, text=True, env={**__import__("os").environ, "HYDROLITE_RUNTIME_DIR":str(runtime)})
        assert result.returncode == 1
        assert process.poll() is None
    finally:
        process.terminate(); process.wait()
