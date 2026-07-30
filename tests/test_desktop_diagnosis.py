from hydrolite.desktop.desktop_diagnosis import build_desktop_diagnosis, write_desktop_diagnosis


def test_diagnosis_writes_json_and_markdown(tmp_path):
    result = build_desktop_diagnosis(tmp_path / "missing.app")
    paths = write_desktop_diagnosis(tmp_path, result=result)
    assert result["architecture"] in {"arm64", "x86_64"}
    assert paths["json"].exists() and paths["markdown"].exists()
