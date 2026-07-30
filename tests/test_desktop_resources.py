from hydrolite.desktop.bundle_resources import detect_missing_resource, locate_bundled_resource, validate_bundle_resources


def test_source_resources_and_escape_guard():
    result = validate_bundle_resources()
    assert result["status"] == "passed"
    assert detect_missing_resource("templates")["exists"]
    try:
        locate_bundled_resource("../outside")
    except ValueError:
        pass
    else:
        raise AssertionError("path escape must fail")


def test_demo_project_template_sources_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert (root / "projects/demo_project/project.yaml").exists()
    assert (root / "projects/demo_project/cases/demo.yaml").exists()
