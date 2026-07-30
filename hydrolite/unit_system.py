from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import re

import pandas as pd


_UNITS = {
    "mm": ("length", 0.001, 0.0), "cm": ("length", 0.01, 0.0), "m": ("length", 1.0, 0.0), "km": ("length", 1000.0, 0.0), "ft": ("length", 0.3048, 0.0),
    "m2": ("area", 1.0, 0.0), "ha": ("area", 10000.0, 0.0), "km2": ("area", 1_000_000.0, 0.0),
    "m3": ("volume", 1.0, 0.0), "万m3": ("volume", 10_000.0, 0.0), "l": ("volume", 0.001, 0.0), "ml": ("volume", 1000.0, 0.0),
    "m3/s": ("flow", 1.0, 0.0), "l/s": ("flow", 0.001, 0.0), "m3/d": ("flow", 1 / 86400, 0.0), "cfs": ("flow", 0.028316846592, 0.0),
    "inch": ("length", 0.0254, 0.0),
    "mg/l": ("concentration", 1.0, 0.0), "ug/l": ("concentration", 0.001, 0.0), "g/l": ("concentration", 1000.0, 0.0),
    "kg/d": ("load", 1.0, 0.0), "t/yr": ("load", 1000 / 365.25, 0.0), "kg/event": ("event_load", 1.0, 0.0),
    "c": ("temperature", 1.0, 0.0), "k": ("temperature", 1.0, -273.15),
}
_ALIASES = {"m²": "m2", "km²": "km2", "m³": "m3", "万 m³": "万m3", "m³/s": "m3/s", "m³/d": "m3/d", "l/s": "l/s", "μg/l": "ug/l", "°c": "c", "cms": "m3/s"}


def normalize_unit_name(unit: str) -> str:
    raw = str(unit).strip().lower().replace(" ", "")
    return _ALIASES.get(str(unit).strip().lower(), _ALIASES.get(raw, raw))


def detect_unit(value_or_field: Any) -> str | None:
    text = str(value_or_field).lower()
    patterns = [("km2", ("km2", "km²")), ("m3/s", ("cms", "m3/s", "m³/s")), ("mg/l", ("mg/l", "mg_l")), ("mm", ("rainfall_mm", "_mm")), ("c", ("temperature_c", "_degc"))]
    return next((unit for unit, aliases in patterns if any(alias in text for alias in aliases)), None)


def validate_unit_compatibility(source_unit: str, target_unit: str) -> dict[str, Any]:
    source, target = normalize_unit_name(source_unit), normalize_unit_name(target_unit)
    if source not in _UNITS or target not in _UNITS:
        return {"status": "unknown_unit", "compatible": False}
    compatible = _UNITS[source][0] == _UNITS[target][0]
    return {"status": "passed" if compatible else "incompatible", "compatible": compatible, "dimension": _UNITS[source][0]}


def convert_unit(values: Iterable[float] | pd.Series, source_unit: str, target_unit: str) -> pd.DataFrame:
    source, target = normalize_unit_name(source_unit), normalize_unit_name(target_unit)
    check = validate_unit_compatibility(source, target)
    if not check["compatible"]:
        raise ValueError(f"Units are not compatible or known: {source_unit} -> {target_unit}")
    src_factor, src_offset = _UNITS[source][1:]
    target_factor, target_offset = _UNITS[target][1:]
    original = pd.to_numeric(pd.Series(values), errors="coerce")
    if check["dimension"] == "temperature":
        normalized = (original + src_offset - target_offset)
        factor = 1.0
    else:
        factor = src_factor / target_factor
        normalized = original * factor
    return pd.DataFrame({"original_value": original, "original_unit": source_unit, "normalized_value": normalized, "normalized_unit": target_unit, "conversion_factor": factor, "conversion_status": "converted"})


def get_standard_unit(dataset_type: str, field: str) -> str | None:
    return {"rainfall_mm": "mm", "precipitation_mm": "mm", "flow_cms": "m3/s", "discharge_cms": "m3/s", "area_km2": "km2", "water_level_m": "m", "temperature_c": "c", "concentration_mg_l": "mg/l", "load_kg_d": "kg/d"}.get(field)


def write_unit_conversion_report(output_dir: str | Path, result: pd.DataFrame | dict[str, Any]) -> Path:
    path = Path(output_dir) / "unit_conversion.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    (result if isinstance(result, pd.DataFrame) else pd.DataFrame([result])).to_excel(path, index=False)
    return path
