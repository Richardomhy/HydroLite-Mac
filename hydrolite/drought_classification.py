from __future__ import annotations

from typing import Any

import pandas as pd


DIAGNOSTIC_DEFAULT_THRESHOLDS = [
    ("extreme_drought", -2.0),
    ("severe_drought", -1.5),
    ("moderate_drought", -1.0),
    ("abnormally_dry", -0.5),
]


def load_drought_thresholds(config: dict[str, Any] | None = None) -> dict[str, Any]:
    values = (config or {}).get("thresholds", DIAGNOSTIC_DEFAULT_THRESHOLDS)
    return {"source": (config or {}).get("source", "diagnostic_default_thresholds"), "thresholds": values}


def classify_drought_value(value: float | None, config: dict[str, Any] | None = None) -> str:
    if value is None or pd.isna(value):
        return "unavailable"
    for name, threshold in load_drought_thresholds(config)["thresholds"]:
        if float(value) <= float(threshold):
            return name
    return "normal"


def classify_drought_series(series: pd.Series, config: dict[str, Any] | None = None) -> pd.Series:
    return series.apply(lambda value: classify_drought_value(value, config)).rename(f"{series.name or 'index'}_class")


def classify_drought_components(components: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    result = components.copy()
    for column in components.select_dtypes(include="number"):
        result[f"{column}_class"] = classify_drought_series(components[column], config)
    result.attrs["threshold_source"] = load_drought_thresholds(config)["source"]
    return result
