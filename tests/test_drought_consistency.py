from hydrolite.drought_consistency import calculate_composite_weight_audit, classify_component_availability

def test_unavailable_reservoir_is_removed(tmp_path):
    result=calculate_composite_weight_audit(classify_component_availability(tmp_path))
    assert result.loc[result.component=="reservoir","effective_weight"].iloc[0]==0
