from hydrolite.ui.navigation import NAVIGATION, list_navigation, term


def test_navigation_has_eight_bilingual_top_level_entries():
    assert [item.nav_id for item in NAVIGATION] == ["home", "projects", "scenarios", "data", "runs", "results", "research", "system"]
    assert [item["label"] for item in list_navigation("中文")] == ["首页", "项目", "场景", "数据", "运行", "成果", "方法实验室", "系统"]
    assert [item["label"] for item in list_navigation("English")] == ["Home", "Projects", "Scenarios", "Data", "Runs", "Results", "Research Lab", "System"]
    assert term("susceptibility") == "易发性" and term("risk") == "风险"


def test_streamlit_top_level_navigation_smoke():
    from streamlit.testing.v1 import AppTest
    for page in ("首页", "项目", "场景", "数据", "运行", "成果", "方法实验室", "系统"):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
        app.sidebar.radio[2].set_value(page).run()
        assert not app.exception, page


def test_streamlit_advanced_experimental_pages_smoke():
    from streamlit.testing.v1 import AppTest

    for navigation, page in (
        ("数据", "GEE 数据集智能"),
        ("方法实验室", "水质方法实验室"),
        ("方法实验室", "洪水易发性"),
    ):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
        app.sidebar.radio[1].set_value("Advanced").run()
        app.sidebar.radio[2].set_value(navigation).run()
        app.sidebar.selectbox[0].set_value(page).run()
        assert not app.exception, page
