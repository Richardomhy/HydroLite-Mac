from hydrolite.ui.app import PAGES
from hydrolite.ui.pages import flood_susceptibility, gee_dataset_intelligence, research_methods_lab


def test_method_lab_pages_are_registered():
    assert callable(gee_dataset_intelligence.render) and callable(research_methods_lab.render) and callable(flood_susceptibility.render)
    assert {"GEE 数据集智能", "水文研究方法实验室", "洪水易发性"}.issubset(PAGES)
