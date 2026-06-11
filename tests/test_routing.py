import numpy as np
import pytest

from hydrolite.routing import muskingum_route, validate_muskingum_parameters


def test_muskingum_keeps_constant_flow_constant():
    inflow = np.full(8, 12.0)
    outflow = muskingum_route(inflow, k_hours=2.0, x=0.2, dt_hours=1.0, reach_id="R1")
    assert np.allclose(outflow, 12.0)


def test_muskingum_valid_parameters_pass():
    validate_muskingum_parameters("R-ok", k_hours=2.0, x=0.2, dt_hours=1.0)


@pytest.mark.parametrize(
    ("k_hours", "x", "dt_hours", "condition"),
    [
        (2.0, -0.1, 1.0, "0 <= X"),
        (2.0, 0.6, 1.0, "X <= 0.5"),
        (0.0, 0.2, 1.0, "K > 0"),
        (2.0, 0.2, 4.0, "dt <= 2*K*(1-X)"),
        (2.0, 0.4, 1.0, "dt >= 2*K*X"),
    ],
)
def test_muskingum_invalid_parameters_report_reach_and_values(
    k_hours, x, dt_hours, condition
):
    with pytest.raises(ValueError) as exc_info:
        validate_muskingum_parameters("R-bad", k_hours=k_hours, x=x, dt_hours=dt_hours)

    message = str(exc_info.value)
    assert "reach_id=R-bad" in message
    assert f"dt={dt_hours}" in message
    assert f"K={k_hours}" in message
    assert f"X={x}" in message
    assert condition in message
    assert "Please adjust dt, K, or X" in message
