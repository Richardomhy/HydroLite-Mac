from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def load_openhydronet_predictions_placeholder(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
    return pd.DataFrame(columns=["datetime", "basin_id", "forecast_flow", "status"])


def write_openhydronet_summary_placeholder(path: str | Path, summary: dict[str, Any] | None = None) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = summary or {
        "run_status": "placeholder",
        "message": "OpenHydroNet postprocessing is not implemented yet.",
    }
    pd.DataFrame([payload]).to_excel(output_path, index=False)
    return output_path


def build_input_quality_report(
    static_attributes: pd.DataFrame,
    meteorological_forcing: pd.DataFrame,
    hydrolite_streamflow: pd.DataFrame,
    observed_streamflow: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    warnings: list[dict[str, Any]] = []

    def check_fields(name: str, df: pd.DataFrame, required: list[str]) -> pd.DataFrame:
        rows = []
        for field in required:
            ok = field in df.columns
            rows.append(
                {
                    "dataset": name,
                    "check_name": f"field:{field}",
                    "status": "passed" if ok else "failed",
                    "message": "field exists" if ok else f"missing required field {field}",
                    "severity": "error" if not ok else "info",
                }
            )
        return pd.DataFrame(rows)

    static_required = [
        "basin_id",
        "gauge_id",
        "area_km2",
        "dem_mean",
        "dem_min",
        "dem_max",
        "surface_water_occurrence_mean",
        "suggested_cn",
        "suggested_lag_hours",
        "suggested_muskingum_k_hours",
        "suggested_muskingum_x",
        "source",
    ]
    met_required = ["datetime", "basin_id", "precipitation_mm", "temperature_mean_c"]
    flow_required = ["datetime", "basin_id", "streamflow_m3s", "source_case"]
    observed_required = ["datetime", "basin_id", "gauge_id", "observed_streamflow_m3s", "source"]

    static_checks = check_fields("static_attributes", static_attributes, static_required)
    met_checks = check_fields("meteorological_forcing", meteorological_forcing, met_required)
    flow_checks = check_fields("hydrolite_streamflow", hydrolite_streamflow, flow_required)
    observed_checks = (
        check_fields("observed_streamflow", observed_streamflow, observed_required)
        if observed_streamflow is not None
        else pd.DataFrame(columns=["dataset", "check_name", "status", "message", "severity"])
    )

    if "precipitation_mm" in meteorological_forcing.columns:
        has_negative = (pd.to_numeric(meteorological_forcing["precipitation_mm"], errors="coerce") < 0).any()
        met_checks = pd.concat(
            [
                met_checks,
                pd.DataFrame(
                    [
                        {
                            "dataset": "meteorological_forcing",
                            "check_name": "precipitation_non_negative",
                            "status": "failed" if has_negative else "passed",
                            "message": "negative precipitation found" if has_negative else "precipitation is non-negative",
                            "severity": "error" if has_negative else "info",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    if "temperature_mean_c" in meteorological_forcing.columns:
        temperature = pd.to_numeric(meteorological_forcing["temperature_mean_c"], errors="coerce")
        non_null = temperature.notna()
        parse_ok = non_null.sum() > 0
        in_range = bool(((temperature[non_null] >= -80) & (temperature[non_null] <= 60)).all()) if parse_ok else False
        coverage = float(non_null.mean()) if len(temperature) else 0.0
        met_checks = pd.concat(
            [
                met_checks,
                pd.DataFrame(
                    [
                        {
                            "dataset": "meteorological_forcing",
                            "check_name": "temperature_numeric",
                            "status": "passed" if parse_ok else "warning",
                            "message": "temperature_mean_c has numeric values"
                            if parse_ok
                            else "temperature_mean_c has no numeric values",
                            "severity": "info" if parse_ok else "warning",
                        },
                        {
                            "dataset": "meteorological_forcing",
                            "check_name": "temperature_reasonable_range_c",
                            "status": "passed" if in_range else "warning",
                            "message": "temperature_mean_c is within -80 to 60 Celsius"
                            if in_range
                            else "temperature_mean_c is missing or outside -80 to 60 Celsius",
                            "severity": "info" if in_range else "warning",
                        },
                        {
                            "dataset": "meteorological_forcing",
                            "check_name": "temperature_coverage",
                            "status": "passed" if coverage >= 0.8 else "warning",
                            "message": f"temperature coverage is {coverage:.1%}",
                            "severity": "info" if coverage >= 0.8 else "warning",
                        },
                    ]
                ),
            ],
            ignore_index=True,
        )
    if "streamflow_m3s" in hydrolite_streamflow.columns:
        has_negative = (pd.to_numeric(hydrolite_streamflow["streamflow_m3s"], errors="coerce") < 0).any()
        flow_checks = pd.concat(
            [
                flow_checks,
                pd.DataFrame(
                    [
                        {
                            "dataset": "hydrolite_streamflow",
                            "check_name": "streamflow_non_negative",
                            "status": "failed" if has_negative else "passed",
                            "message": "negative streamflow found" if has_negative else "streamflow is non-negative",
                            "severity": "error" if has_negative else "info",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    observed_time = pd.Series(dtype="datetime64[ns]")
    if observed_streamflow is not None and "observed_streamflow_m3s" in observed_streamflow.columns:
        observed_values = pd.to_numeric(observed_streamflow["observed_streamflow_m3s"], errors="coerce")
        bad_observed = observed_values.isna().any() or (observed_values < 0).any()
        observed_checks = pd.concat(
            [
                observed_checks,
                pd.DataFrame(
                    [
                        {
                            "dataset": "observed_streamflow",
                            "check_name": "observed_streamflow_non_negative",
                            "status": "failed" if bad_observed else "passed",
                            "message": "observed_streamflow_m3s must be numeric and non-negative"
                            if bad_observed
                            else "observed streamflow is numeric and non-negative",
                            "severity": "error" if bad_observed else "info",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    met_time = pd.to_datetime(meteorological_forcing.get("datetime"), errors="coerce")
    flow_time = pd.to_datetime(hydrolite_streamflow.get("datetime"), errors="coerce")
    if observed_streamflow is not None:
        observed_time = pd.to_datetime(observed_streamflow.get("datetime"), errors="coerce")
        observed_checks = pd.concat(
            [
                observed_checks,
                pd.DataFrame(
                    [
                        {
                            "dataset": "observed_streamflow",
                            "check_name": "datetime_parseable",
                            "status": "failed" if observed_time.isna().any() else "passed",
                            "message": "unparseable datetime found" if observed_time.isna().any() else "datetime parseable",
                            "severity": "error" if observed_time.isna().any() else "info",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    met_checks = pd.concat(
        [
            met_checks,
            pd.DataFrame(
                [
                    {
                        "dataset": "meteorological_forcing",
                        "check_name": "datetime_parseable",
                        "status": "failed" if met_time.isna().any() else "passed",
                        "message": "unparseable datetime found" if met_time.isna().any() else "datetime parseable",
                        "severity": "error" if met_time.isna().any() else "info",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    flow_checks = pd.concat(
        [
            flow_checks,
            pd.DataFrame(
                [
                    {
                        "dataset": "hydrolite_streamflow",
                        "check_name": "datetime_parseable",
                        "status": "failed" if flow_time.isna().any() else "passed",
                        "message": "unparseable datetime found" if flow_time.isna().any() else "datetime parseable",
                        "severity": "error" if flow_time.isna().any() else "info",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    overlap = False
    if not met_time.dropna().empty and not flow_time.dropna().empty:
        overlap = met_time.min() <= flow_time.max() and flow_time.min() <= met_time.max()
    overview_rows = [
        {
            "check_name": "time_range_overlap",
            "status": "passed" if overlap else "failed",
            "message": "meteorological forcing and streamflow time ranges overlap"
            if overlap
            else "meteorological forcing and streamflow time ranges do not overlap",
            "severity": "error" if not overlap else "info",
        }
    ]

    basin_sets = []
    for df in (static_attributes, meteorological_forcing, hydrolite_streamflow):
        if "basin_id" in df.columns:
            basin_sets.append(set(df["basin_id"].dropna().astype(str)))
    basin_consistent = bool(basin_sets) and len(set.union(*basin_sets)) == 1
    overview_rows.append(
        {
            "check_name": "basin_id_consistency",
            "status": "passed" if basin_consistent else "failed",
            "message": "basin_id is consistent" if basin_consistent else "basin_id differs across package files",
            "severity": "error" if not basin_consistent else "info",
        }
    )
    if observed_streamflow is not None:
        observed_overlap = False
        if not met_time.dropna().empty and not observed_time.dropna().empty:
            observed_overlap = met_time.min() <= observed_time.max() and observed_time.min() <= met_time.max()
        overview_rows.append(
            {
                "check_name": "observed_meteorological_time_range_overlap",
                "status": "passed" if observed_overlap else "failed",
                "message": "observed streamflow and meteorological forcing time ranges overlap"
                if observed_overlap
                else "observed streamflow and meteorological forcing time ranges do not overlap",
                "severity": "error" if not observed_overlap else "info",
            }
        )

    if "temperature_mean_c" in meteorological_forcing.columns and pd.to_numeric(
        meteorological_forcing["temperature_mean_c"], errors="coerce"
    ).isna().all():
        warnings.append(
            {
                "warning_name": "temperature_mean_c_all_na",
                "message": "temperature_mean_c is all NA because temperature data is unavailable or did not align by date.",
                "severity": "warning",
            }
        )
    if observed_streamflow is None:
        warnings.append(
            {
                "warning_name": "observed_streamflow_missing",
                "message": "No real observed streamflow file was found; hydrolite_streamflow is simulated output.",
                "severity": "warning",
            }
        )

    overview = pd.DataFrame(overview_rows)
    warnings_df = pd.DataFrame(warnings, columns=["warning_name", "message", "severity"])
    return {
        "overview": overview,
        "static_attributes_checks": static_checks,
        "meteorological_checks": met_checks,
        "streamflow_checks": flow_checks,
        "observed_streamflow_checks": observed_checks,
        "warnings": warnings_df,
    }


def write_input_quality_report(path: str | Path, sheets: dict[str, pd.DataFrame]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path) as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    return output_path
