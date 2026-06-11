from hydrolite.hydrology import scs_cn_runoff_depth_mm, triangular_unit_hydrograph
from hydrolite.hydrology import runoff_to_flow_cms
import pandas as pd


def test_scs_cn_no_runoff_below_initial_abstraction():
    assert scs_cn_runoff_depth_mm(1.0, 75) == 0.0


def test_scs_cn_positive_runoff_for_large_storm():
    assert scs_cn_runoff_depth_mm(80.0, 80) > 0.0


def test_unit_hydrograph_weights_sum_to_one():
    weights = triangular_unit_hydrograph(lag_hours=2.0, dt_hours=1.0)
    assert abs(weights.sum() - 1.0) < 1e-12


def test_unit_hydrograph_routing_preserves_direct_runoff_volume():
    rainfall = pd.DataFrame(
        {"time": pd.date_range("2026-01-01", periods=3, freq="h"), "rain_mm": [0, 80, 0]}
    )
    subcatchments = pd.DataFrame(
        [{"id": "S1", "area_km2": 1.0, "curve_number": 80, "lag_hours": 2.0}]
    )
    routed = runoff_to_flow_cms(rainfall, subcatchments, dt_hours=1.0)
    expected_depth_mm = scs_cn_runoff_depth_mm(80, 80)
    expected_volume_m3 = expected_depth_mm / 1000 * 1_000_000
    routed_volume_m3 = routed["inflow_cms"].sum() * 3600
    assert abs(routed_volume_m3 - expected_volume_m3) < 1e-6
