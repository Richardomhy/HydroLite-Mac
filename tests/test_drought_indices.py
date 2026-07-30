import numpy as np
import pandas as pd

from hydrolite.drought_indices import calculate_composite_drought_index, calculate_soil_moisture_percentile, calculate_spei, calculate_spi, calculate_ssi


def test_drought_indices_scales_and_percentiles():
    index=pd.date_range("2000-01-01",periods=240,freq="MS")
    rain=pd.Series(np.random.default_rng(4).gamma(2,30,240),index=index)
    pet=pd.Series(50+np.sin(np.arange(240)/12),index=index)
    spi=calculate_spi(rain,3);spei=calculate_spei(rain,pet,3);ssi=calculate_ssi(rain/10,3)
    assert all(len(value)==240 for value in (spi,spei,ssi))
    assert calculate_soil_moisture_percentile(rain).between(0,100).all()
    assert calculate_composite_drought_index(pd.DataFrame({"spi":spi,"spei":spei}),{"spi":0.5,"spei":0.5}).notna().any()
