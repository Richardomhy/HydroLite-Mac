"""Write registry artifacts from metadata only; never include source assets."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from hydrolite.provenance import experiment_output_path, is_protected_path
from hydrolite.research_intake import assess_method_readiness, list_methods, list_sources
from hydrolite.research_status import CLEAN_ROOM_NOTICE
from hydrolite.research_validation import validate_research_registry
from hydrolite.source_licensing import assess_source_license


def _stringify_lists(row: dict[str, object]) -> dict[str, object]:
    return {key: "; ".join(value) if isinstance(value, list) else value for key, value in row.items()}


def write_research_reports(output_dir: str | Path | None = None) -> dict[str, Path]:
    root = Path(output_dir).resolve() if output_dir else experiment_output_path("research_methods")
    if is_protected_path(root):
        raise ValueError(f"Protected path cannot receive research reports: {root}")
    root.mkdir(parents=True, exist_ok=True)
    sources = list_sources(); methods = list_methods()
    validation = validate_research_registry(sources, methods)
    source_rows = [_stringify_lists(item.as_dict()) for item in sources]
    method_rows = [_stringify_lists(item.as_dict()) for item in methods]
    licenses = [assess_source_license(item).as_dict() for item in sources]
    matrix = []
    for card in methods:
        readiness = assess_method_readiness(card, sources)
        matrix.append({
            "method_id": card.method_id,
            "source_ids": "; ".join(card.source_ids),
            "target_component": "; ".join(card.HydroLite_target_components),
            "integration_mode": card.recommended_integration_mode,
            "method_status": card.current_status,
            "readiness": readiness["readiness"],
            "value_added_gate": card.value_added_gate,
            "causal_constraints": card.causal_constraints,
            "physical_constraints": card.physical_constraints,
            "limitations": card.limitations,
        })
    paths = {
        "sources": root / "research_sources.xlsx",
        "methods": root / "research_methods.xlsx",
        "licenses": root / "source_license_assessments.xlsx",
        "integration_matrix": root / "method_integration_matrix.xlsx",
        "registry_json": root / "research_registry.json",
        "validation_json": root / "research_validation.json",
        "report_zh": root / "method_inspiration_report_zh.md",
        "report_en": root / "method_inspiration_report_en.md",
    }
    pd.DataFrame(source_rows).to_excel(paths["sources"], index=False)
    pd.DataFrame(method_rows).to_excel(paths["methods"], index=False)
    pd.DataFrame([_stringify_lists(row) for row in licenses]).to_excel(paths["licenses"], index=False)
    pd.DataFrame(matrix).to_excel(paths["integration_matrix"], index=False)
    paths["registry_json"].write_text(json.dumps({"notice": CLEAN_ROOM_NOTICE, "sources": source_rows, "methods": method_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["validation_json"].write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    source_list = "\n".join(f"- `{item.source_id}`: {item.verification_status}" for item in sources)
    method_list = "\n".join(f"- `{item.method_id}`: {item.current_status}, value_added={item.value_added_gate}" for item in methods)
    paths["report_zh"].write_text(
        f"# HydroLite 方法借鉴登记\n\n{CLEAN_ROOM_NOTICE}\n\n## 来源\n{source_list}\n\n## 方法卡\n{method_list}\n\n所有记录仅为元数据和独立实现准入边界；不包含论文正文、图表或第三方代码。\n",
        encoding="utf-8",
    )
    paths["report_en"].write_text(
        f"# HydroLite Method Inspiration Registry\n\n{CLEAN_ROOM_NOTICE}\n\n## Sources\n{source_list}\n\n## Method cards\n{method_list}\n\nThese are metadata-only clean-room admission records, not source-model reproductions.\n",
        encoding="utf-8",
    )
    return paths
