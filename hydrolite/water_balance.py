from __future__ import annotations

from pathlib import Path

import pandas as pd

from hydrolite.hydrology import scs_cn_runoff_depth_mm


def _balance_error_percent(error_m3: float, reference_m3: float) -> float:
    if reference_m3 == 0:
        return 0.0 if error_m3 == 0 else float("inf")
    return error_m3 / reference_m3 * 100.0


def build_water_balance(
    *,
    case_name: str,
    rainfall: pd.DataFrame,
    subcatchments: pd.DataFrame,
    result: pd.DataFrame,
    dt_hours: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    subbasin_rows = []
    total_rainfall_mm = float(rainfall["rain_mm"].sum())

    for row in subcatchments.itertuples(index=False):
        subbasin_id = str(row.id)
        area_km2 = float(row.area_km2)
        effective_rainfall_mm = sum(
            scs_cn_runoff_depth_mm(float(rain), float(row.curve_number))
            for rain in rainfall["rain_mm"]
        )
        runoff_volume_m3 = effective_rainfall_mm / 1000.0 * area_km2 * 1_000_000.0
        routed_column = f"subcatchment_{subbasin_id}_flow_cms"
        routed_volume_m3 = float(result[routed_column].sum() * dt_hours * 3600.0)
        balance_error_m3 = routed_volume_m3 - runoff_volume_m3

        subbasin_rows.append(
            {
                "subbasin_id": subbasin_id,
                "area_km2": area_km2,
                "total_rainfall_mm": total_rainfall_mm,
                "effective_rainfall_mm": effective_rainfall_mm,
                "runoff_volume_m3": runoff_volume_m3,
                "routed_volume_m3": routed_volume_m3,
                "balance_error_m3": balance_error_m3,
                "balance_error_percent": _balance_error_percent(
                    balance_error_m3, runoff_volume_m3
                ),
            }
        )

    total_inflow_volume_m3 = float(result["inflow_cms"].sum() * dt_hours * 3600.0)
    total_outflow_volume_m3 = float(result["outflow_cms"].sum() * dt_hours * 3600.0)
    outlet_error_m3 = total_outflow_volume_m3 - total_inflow_volume_m3
    outlet_balance = pd.DataFrame(
        [
            {
                "case_name": case_name,
                "total_inflow_volume_m3": total_inflow_volume_m3,
                "total_outflow_volume_m3": total_outflow_volume_m3,
                "balance_error_m3": outlet_error_m3,
                "balance_error_percent": _balance_error_percent(
                    outlet_error_m3, total_inflow_volume_m3
                ),
            }
        ]
    )

    return pd.DataFrame(subbasin_rows), outlet_balance


def write_water_balance(
    path: Path,
    subbasin_balance: pd.DataFrame,
    outlet_balance: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(path) as writer:
        subbasin_balance.to_excel(writer, sheet_name="subbasin_balance", index=False)
        outlet_balance.to_excel(writer, sheet_name="outlet_balance", index=False)


def balance_warning_messages(
    subbasin_balance: pd.DataFrame,
    outlet_balance: pd.DataFrame,
    threshold_percent: float = 5.0,
) -> list[str]:
    messages = []
    for row in subbasin_balance.itertuples(index=False):
        error = float(row.balance_error_percent)
        if abs(error) > threshold_percent:
            messages.append(
                f"Subbasin {row.subbasin_id} water balance error is {error:.3f}%"
            )

    outlet_error = float(outlet_balance["balance_error_percent"].iloc[0])
    if abs(outlet_error) > threshold_percent:
        messages.append(f"Outlet water balance error is {outlet_error:.3f}%")
    return messages

