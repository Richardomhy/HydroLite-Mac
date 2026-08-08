from __future__ import annotations

from pathlib import Path
import yaml

from hydrolite.gee_catalog.loader import load_catalog_records


ROOT = Path(__file__).resolve().parents[2]


def _rules() -> dict:
    return yaml.safe_load((ROOT / "config" / "data_sources" / "gee_datasets.yaml").read_text(encoding="utf-8")).get("use_case_rules", {})


def recommend_datasets(model_id: str, config: str | None = None) -> dict:
    rule = _rules().get(model_id)
    if not rule: return {"status": "unknown_use_case", "model_id": model_id, "recommendations": []}
    needs = {item.lower() for item in rule.get("preferred_characteristics", [])}
    recommendations = []
    for row in load_catalog_records():
        text = " ".join(row.get("hydrolite_use_cases", []) + row.get("categories", []) + row.get("keywords", [])).lower()
        passed = sorted(term for term in needs if term in text)
        score = round(100 * len(passed) / max(len(needs), 1), 1)
        if score:
            recommendations.append({"asset_id": row["asset_id"], "suitability_score": score, "score_components": {"matched_preferred_characteristics": passed, "total_requested": len(needs)}, "hard_conditions_passed": passed, "hard_conditions_failed": sorted(needs - set(passed)), "time_range": [row.get("start_date"), row.get("end_date")], "resolution_m": row.get("nominal_scale_m"), "bands": row.get("bands", []), "units": [band.get("unit") for band in row.get("bands", []) if isinstance(band, dict)], "preprocessing_requirements": rule.get("preprocessing_notes", []), "data_status": row.get("status"), "license": row.get("license_text"), "citation": row.get("citation"), "official_url": row.get("official_catalog_url") or row.get("official_url"), "fallback": rule.get("fallback_characteristics", []), "limitations": row.get("warnings", []) + ["runtime_footprint_check_required"]})
    return {"status": "passed", "model_id": model_id, "config": config, "recommendations": sorted(recommendations, key=lambda item: item["suitability_score"], reverse=True)}
