from __future__ import annotations

from typing import Any

import pandas as pd


REQUIRED_FORECAST_FIELDS = (
    "issue_time", "valid_start", "valid_end", "lead_month", "member_id",
    "variable", "value", "unit", "subbasin_id", "source", "forecast_system",
    "initialization_time", "scenario_type", "bias_correction", "quality_status",
)
ALLOWED_SCENARIO_TYPES = {
    "seasonal_forecast", "weather_forecast", "climatology", "persistence",
    "user_scenario", "synthetic_demo",
}
ALLOWED_VARIABLES = {"precipitation", "temperature", "PET", "soil_moisture", "streamflow", "reservoir_inflow"}


def validate_drought_forecast_forcing(data: pd.DataFrame) -> dict[str, Any]:
    missing = sorted(set(REQUIRED_FORECAST_FIELDS) - set(data.columns))
    errors: list[str] = []
    if not missing:
        if not set(data["scenario_type"].dropna()) <= ALLOWED_SCENARIO_TYPES:
            errors.append("scenario_type contains unsupported values")
        if not set(data["variable"].dropna()) <= ALLOWED_VARIABLES:
            errors.append("variable contains unsupported values")
        for column in ("issue_time", "valid_start", "valid_end", "initialization_time"):
            if pd.to_datetime(data[column], errors="coerce").isna().any():
                errors.append(f"{column} contains unparseable timestamps")
        if (pd.to_numeric(data["lead_month"], errors="coerce") < 0).any():
            errors.append("lead_month must be non-negative")
    forecast_types = set(data.get("scenario_type", []))
    is_published_forecast = bool(forecast_types & {"seasonal_forecast", "weather_forecast"})
    return {
        "status": "passed" if not missing and not errors else "failed",
        "missing": missing,
        "errors": errors,
        "mode": "forecast" if is_published_forecast else "scenario_simulation",
        "forecast_label_allowed": is_published_forecast,
    }
