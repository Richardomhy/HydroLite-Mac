from hydrolite.desktop.backend import build_streamlit_command, build_streamlit_environment, locate_streamlit_entrypoint


def test_backend_command_is_loopback_and_dynamic(tmp_path):
    command = build_streamlit_command(49123, tmp_path)
    assert "127.0.0.1" in command and "49123" in command
    assert "8501" not in command
    assert "--global.developmentMode" in command
    assert locate_streamlit_entrypoint().name == "streamlit_app.py"
    assert build_streamlit_environment(tmp_path)["HYDROLITE_RUNTIME_DIR"] == str(tmp_path.resolve())
