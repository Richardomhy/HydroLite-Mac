from hydrolite.icesat2 import DEMO, build_waterbody_depth_constraint, extract_atl13_water_data, filter_icesat2_quality, estimate_icesat2_water_depth
def test_sparse_constraint_not_continuous_surface():
    data=estimate_icesat2_water_depth(filter_icesat2_quality(extract_atl13_water_data(DEMO/"demo_atl13_extract.csv"),"ATL13"))
    assert data["corrected_depth_m"].dropna().gt(0).all()
    assert build_waterbody_depth_constraint(data,DEMO/"demo_waterbody.geojson")["surface"] is None
