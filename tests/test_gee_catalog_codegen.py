from hydrolite.gee_catalog.codegen import generate_ee_code


def test_codegen_requires_real_band_and_never_executes():
    needs_band = generate_ee_code("UCSB-CHG/CHIRPS/DAILY")
    assert needs_band["status"] == "band_selection_required"
    code = generate_ee_code("UCSB-CHG/CHIRPS/DAILY", band="precipitation")
    assert code["status"] == "authentication_required"
    assert code["execution"] == "not_executed"
    assert "Export" not in code["snippet"]
