from hydrolite.hierarchical_multihorizon import optimize_blend_on_validation


def test_blend_fits_validation_only(): assert optimize_blend_on_validation([1,2],[1,1],[1,2])["fit_data"] == "validation_only"
