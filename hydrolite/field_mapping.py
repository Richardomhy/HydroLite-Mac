from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
import json
import re
from typing import Any

import pandas as pd

from hydrolite.data_registry import get_dataset_type


ALIASES = {
    "timestamp": ["time", "datetime", "date_time", "时间", "日期时间", "日期"],
    "rainfall_mm": ["rainfall", "rain_mm", "precipitation_mm", "precip", "降雨", "降雨量"],
    "flow_cms": ["flow", "discharge", "outlet_flow", "流量", "径流量"],
    "water_level_m": ["water_level", "stage_m", "水位"],
    "temperature_c": ["temperature", "temp", "气温", "温度"],
    "station_id": ["station", "site_id", "站点", "站号"],
    "longitude": ["lon", "lng", "x", "经度"],
    "latitude": ["lat", "y", "纬度"],
    "subbasin_id": ["subbasin", "subcatchment_id", "子流域"],
    "reach_id": ["reach", "river_id", "河段"],
    "concentration_mg_l": ["concentration", "conc", "浓度"],
    "load_kg_d": ["load", "负荷"],
    "discharge_cms": ["discharge", "排放流量"],
    "area_km2": ["area", "basin_area", "面积"],
    "elevation_m": ["elevation", "elev", "高程"],
}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def score_field_match(source_field: str, target_field: str) -> dict[str, Any]:
    source, target = _norm(source_field), _norm(target_field)
    if source == target:
        return {"score": 1.0, "reason": "exact normalized match"}
    aliases = {_norm(alias) for alias in ALIASES.get(target_field, [])}
    if source in aliases:
        return {"score": 0.95, "reason": "known Chinese/English alias"}
    score = SequenceMatcher(None, source, target).ratio()
    return {"score": round(score, 3), "reason": "name similarity"}


def build_mapping_candidates(dataset: pd.DataFrame, dataset_type: str | dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    spec = get_dataset_type(dataset_type) if isinstance(dataset_type, str) else dataset_type
    targets = spec["required_fields"] + spec.get("optional_fields", [])
    return {
        target: sorted(
            [{"source_field": source, **score_field_match(str(source), target)} for source in dataset.columns],
            key=lambda item: item["score"],
            reverse=True,
        )[:3]
        for target in targets
    }


def infer_field_mapping(dataset: pd.DataFrame, dataset_type: str | dict[str, Any]) -> dict[str, Any]:
    candidates = build_mapping_candidates(dataset, dataset_type)
    mapping, details = {}, []
    for target, options in candidates.items():
        best = options[0] if options else {"source_field": None, "score": 0.0, "reason": "no fields"}
        accepted = best["score"] >= 0.8
        if accepted:
            mapping[best["source_field"]] = target
        details.append({"target_field": target, "selected_source": best["source_field"], "confidence": best["score"], "alternatives": options[1:], "reason": best["reason"], "user_confirmation_required": best["score"] < 0.9})
    required = (get_dataset_type(dataset_type) if isinstance(dataset_type, str) else dataset_type)["required_fields"]
    missing = [field for field in required if field not in mapping.values()]
    return {"status": "passed" if not missing and not any(row["user_confirmation_required"] for row in details if row["target_field"] in required) else ("needs_confirmation" if not missing else "needs_mapping"), "mapping": mapping, "details": details, "missing_required": missing}


def apply_field_mapping(dataset: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    return dataset.rename(columns=mapping).copy()


def validate_field_mapping(mapping: dict[str, str], dataset_type: str | dict[str, Any]) -> dict[str, Any]:
    spec = get_dataset_type(dataset_type) if isinstance(dataset_type, str) else dataset_type
    targets = list(mapping.values())
    missing = [field for field in spec["required_fields"] if field not in targets]
    duplicates = sorted({field for field in targets if targets.count(field) > 1})
    return {"status": "passed" if not missing and not duplicates else "failed", "missing_required": missing, "duplicate_targets": duplicates}


def save_field_mapping(mapping: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_field_mapping(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_field_mapping_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = save_field_mapping(result, output / "field_mapping.json")
    xlsx_path = output / "field_mapping.xlsx"
    pd.DataFrame(result.get("details", [])).to_excel(xlsx_path, index=False)
    return {"json": json_path, "xlsx": xlsx_path}
