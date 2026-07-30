from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import math

import pandas as pd


def calculate_mapping_distance(mapping: dict[str, Any]) -> float | None:
    if all(mapping.get(name) is not None for name in ("station_lon", "station_lat", "element_lon", "element_lat")):
        dx = (float(mapping["station_lon"]) - float(mapping["element_lon"])) * 111_320 * math.cos(math.radians(float(mapping["station_lat"])))
        dy = (float(mapping["station_lat"]) - float(mapping["element_lat"])) * 110_540
        return float((dx * dx + dy * dy) ** 0.5)
    return None


def classify_mapping_confidence(mapping: dict[str, Any]) -> str:
    if mapping.get("explicit_element_id"):
        return "high"
    distance = calculate_mapping_distance(mapping)
    if mapping.get("topology_confirmed") and distance is not None and distance <= 500:
        return "high"
    if distance is not None and distance <= 2_000:
        return "medium"
    return "low"


def map_flow_station_to_reach(station: dict[str, Any], reaches: Any) -> dict[str, Any]:
    rows = reaches.to_dict("records") if isinstance(reaches, pd.DataFrame) else list(reaches or [])
    explicit = station.get("element_id") or station.get("reach_id")
    match = next((row for row in rows if str(row.get("reach_id", row.get("id"))) == str(explicit)), None)
    if match is None and len(rows) == 1:
        match = rows[0]
    mapping = {
        "station_id": station.get("station_id"),
        "variable": station.get("variable", "flow"),
        "model_element_type": "reach",
        "model_element_id": None if match is None else match.get("reach_id", match.get("id")),
        "explicit_element_id": bool(explicit and match),
        "topology_confirmed": bool(station.get("topology_confirmed", False)),
        "station_lon": station.get("longitude"),
        "station_lat": station.get("latitude"),
        "element_lon": None if match is None else match.get("longitude"),
        "element_lat": None if match is None else match.get("latitude"),
        "mapping_method": "explicit_element_id" if explicit and match else "single_outlet" if match else "unmapped",
    }
    mapping["distance_m"] = calculate_mapping_distance(mapping)
    mapping["confidence"] = classify_mapping_confidence(mapping)
    mapping["manual_confirmation_required"] = mapping["confidence"] == "low"
    return mapping


def map_stage_station_to_reservoir(station: dict[str, Any], reservoirs: Any) -> dict[str, Any]:
    rows = reservoirs.to_dict("records") if isinstance(reservoirs, pd.DataFrame) else list(reservoirs or [])
    explicit = station.get("element_id") or station.get("reservoir_id")
    match = next((row for row in rows if str(row.get("reservoir_id", row.get("id"))) == str(explicit)), None)
    mapping = {
        "station_id": station.get("station_id"), "variable": station.get("variable", "stage"),
        "model_element_type": "reservoir", "model_element_id": None if match is None else match.get("reservoir_id", match.get("id")),
        "explicit_element_id": bool(explicit and match), "topology_confirmed": False,
        "mapping_method": "explicit_element_id" if match else "unmapped",
    }
    mapping["distance_m"] = None
    mapping["confidence"] = "high" if match else "low"
    mapping["manual_confirmation_required"] = not bool(match)
    return mapping


def map_station_to_model_element(station: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    variable = str(station.get("variable", "")).lower()
    if variable in {"stage", "water_level", "reservoir_stage"}:
        return map_stage_station_to_reservoir(station, project.get("reservoirs", []))
    return map_flow_station_to_reach(station, project.get("reaches", []))


def validate_observation_mapping(mapping: dict[str, Any] | pd.DataFrame) -> dict[str, Any]:
    rows = mapping.to_dict("records") if isinstance(mapping, pd.DataFrame) else [mapping]
    errors = [str(row.get("station_id")) for row in rows if not row.get("model_element_id")]
    low = [str(row.get("station_id")) for row in rows if row.get("confidence") == "low"]
    return {"status": "passed" if not errors else "needs_manual_review", "unmapped": errors, "low_confidence": low}


def write_observation_mapping_report(output_dir: str | Path, result: pd.DataFrame | list[dict[str, Any]]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame = result if isinstance(result, pd.DataFrame) else pd.DataFrame(result)
    xlsx = output / "station_model_mapping.xlsx"
    frame.to_excel(xlsx, index=False)
    features = []
    for row in frame.to_dict("records"):
        if pd.notna(row.get("station_lon")) and pd.notna(row.get("station_lat")):
            features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [row["station_lon"], row["station_lat"]]}, "properties": {key: value for key, value in row.items() if key not in {"station_lon", "station_lat"} and pd.notna(value)}})
    geojson = output / "station_model_mapping.geojson"
    geojson.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2), encoding="utf-8")
    validation = validate_observation_mapping(frame)
    report = output / "station_model_mapping_report.md"
    report.write_text(
        "# Station to Model Mapping Report\n\n"
        f"- Mapping count: `{len(frame)}`\n- Low confidence: `{len(validation['low_confidence'])}`\n"
        "- Low-confidence nearest mappings require manual confirmation and are not automatically accepted.\n",
        encoding="utf-8",
    )
    return {"xlsx": xlsx, "geojson": geojson, "report": report}
