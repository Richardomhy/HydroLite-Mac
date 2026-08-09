from pathlib import Path


def test_delivery_ui_exposes_separate_statuses_and_no_ignore_all():
    project_source = Path("hydrolite/ui/pages/project_center.py").read_text(encoding="utf-8")
    results_source = Path("hydrolite/ui/pages/results_center.py").read_text(encoding="utf-8")
    assert "Scientific Validation / 科学验证" in project_source
    assert "Delivery Review / 交付审核" in project_source
    assert "Delivery Readiness Checklist" in project_source
    assert "Acknowledge {code}" in project_source
    assert "ignore all" not in project_source.casefold()
    assert "Frozen Deliverables" in results_source


def test_project_results_system_streamlit_apptest():
    from streamlit.testing.v1 import AppTest
    for navigation in ("项目", "成果", "系统"):
        app = AppTest.from_file("streamlit_app.py", default_timeout=45).run()
        app.sidebar.radio[2].set_value(navigation).run()
        assert not app.exception, navigation
