from pathlib import Path
import pytest
from hydrolite.sediment_delivery import calculate_reservoir_trapping_efficiency, run_sediment_demo, validate_sdr_config
ROOT=Path(__file__).resolve().parents[1]
def test_sediment_demo():
    result=run_sediment_demo();assert result['delivered_hillslope_sediment_t_yr']==52;assert result['released_sediment_t_yr']==20.8
def test_sdr_range():
    with pytest.raises(ValueError): validate_sdr_config({'mode':'user_defined','sdr':1.1})
    with pytest.raises(ValueError): calculate_reservoir_trapping_efficiency({}, {'mode':'user_defined','trapping_efficiency':-0.1})
