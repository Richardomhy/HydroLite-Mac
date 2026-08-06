from hydrolite.water_quality_experiment import assess_water_quality_experiment


def test_water_quality_stays_planned():
    result=assess_water_quality_experiment(); assert result["water_quality"]=="planned" and result["water_quality_method_lab"]=="partial"
