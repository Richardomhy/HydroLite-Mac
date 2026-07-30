from hydrolite.hec_hms import discover_hms_reservoir_reference_projects
def test_reference_discovery_is_bounded():
    refs=discover_hms_reservoir_reference_projects();assert any(x['project_name']=='river_bend' for x in refs)
