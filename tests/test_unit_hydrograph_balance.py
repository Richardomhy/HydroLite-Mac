import numpy as np
from hydrolite.hydrology import scs_cn_excess_rainfall_increments_mm, scs_cn_runoff_depth_mm, triangular_unit_hydrograph
def test_cumulative_scs_cn_becomes_incremental_excess():
    rain=np.array([10.,20.,30.]);ex=scs_cn_excess_rainfall_increments_mm(rain,75,.2)
    assert np.isclose(ex.sum(),scs_cn_runoff_depth_mm(rain.sum(),75,.2))
def test_unit_hydrograph_weights_conserve_volume(): assert np.isclose(triangular_unit_hydrograph(2,1).sum(),1)
