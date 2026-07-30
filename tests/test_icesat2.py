from hydrolite.icesat2 import DEMO, run_icesat2_demo, select_icesat2_product_for_waterbody
def test_icesat2_demo_and_selection(tmp_path):
    assert select_icesat2_product_for_waterbody("inland_reservoir","depth")["recommended_product"] == "ATL13"
    result=run_icesat2_demo(tmp_path)
    assert result["validation"]["status"] == "passed"
    assert (tmp_path/"depth_profiles.csv").exists()
