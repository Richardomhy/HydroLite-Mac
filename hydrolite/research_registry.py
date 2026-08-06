from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


NOTICE = "本实现借鉴公开论文中的通用方法思想，为 HydroLite 独立设计，不构成原论文模型的精确复现。"


def built_in_sources() -> list[dict[str, Any]]:
    """Clean-room method records. No paper text, figures, or external code are stored."""
    return [
        {"source_id": "gamma_lag_feature_method", "title": "融合先验信息与深度学习的小样本水文建模", "authors": "Yang et al.", "journal": "水科学进展", "year": 2026, "doi": "10.14042/j.cnki.32.1309.2026.04.002", "urls": ["https://link.cnki.net/doi/10.14042/j.cnki.32.1309.2026.04.002"], "abstract": "Method concepts only: Gamma-shaped causal lag, multi-timescale nonnegative components, and prior-constrained correction.", "full_text_available": False, "source_license": "copyrighted_literature", "code_available": False, "code_license": "not_applicable", "implementation_mode": "method_inspired_clean_room", "borrowed_concepts": ["causal gamma lag", "fast/medium/slow components", "nonnegative weights", "small-sample priors"], "excluded_elements": ["paper network", "training configuration", "loss replication", "metric replication"], "hydrolite_component": "gamma_lag_features", "limitations": "Synthetic demonstrations are not project validation.", "provenance": "bibliographic metadata and public abstract only"},
        {"source_id": "trend_graph_multihorizon_water_quality", "title": "A spatial-temporal trend-aware neural network model for accurate water quality prediction in river", "authors": "Not reproduced", "journal": "Water Research", "year": 2025, "doi": "10.1016/j.watres.2025.124389", "urls": ["https://doi.org/10.1016/j.watres.2025.124389"], "abstract": "Method concepts only: trend features, directed station graph, and independent forecast horizons.", "full_text_available": False, "source_license": "copyrighted_literature", "code_available": False, "code_license": "not_applicable", "implementation_mode": "method_inspired_clean_room", "borrowed_concepts": ["trend-aware features", "river graph", "multi-horizon evaluation"], "excluded_elements": ["STTNN architecture", "attention equations", "paper dataset"], "hydrolite_component": "water_quality_method_lab", "limitations": "Water-quality capability remains planned.", "provenance": "DOI metadata only"},
        {"source_id": "adaptive_flood_susceptibility_xai", "title": "A reinforcement learning approach with explainable AI for spatial flood susceptibility analysis", "authors": "Not reproduced", "journal": "Journal of Hydrology: Regional Studies", "year": 2025, "doi": "10.1016/j.ejrh.2025.103035", "urls": ["https://doi.org/10.1016/j.ejrh.2025.103035"], "abstract": "Method concepts only: conditioning factors, spatial validation, optional policy learning, and explanation stability.", "full_text_available": False, "source_license": "copyrighted_literature", "code_available": False, "code_license": "not_applicable", "implementation_mode": "method_inspired_clean_room", "borrowed_concepts": ["spatial validation", "optional adaptive selection", "global and local explanations"], "excluded_elements": ["RL-Stack", "paper reward", "paper maps"], "hydrolite_component": "flood_susceptibility", "limitations": "RL is not recommended without demonstrated value.", "provenance": "DOI metadata only"},
        {"source_id": "physics_graph_temporal_residual", "title": "Enhancing hydrological simulation and climate change impact assessment for the Poyang Lake Region, China: A novel hybrid SWAT-GCN-BiLSTM framework", "authors": "Not reproduced", "journal": "Journal of Hydrology: Regional Studies", "year": 2026, "doi": "10.1016/j.ejrh.2026.103145", "urls": ["https://doi.org/10.1016/j.ejrh.2026.103145"], "abstract": "Method concepts only: physics-state graph features and causality-safe residual correction.", "full_text_available": False, "source_license": "copyrighted_literature", "code_available": False, "code_license": "not_applicable", "implementation_mode": "method_inspired_clean_room", "borrowed_concepts": ["physical states as graph nodes", "directed reach edges", "residual correction"], "excluded_elements": ["SWAT replacement", "GCN-BiLSTM architecture", "CMIP6 conclusions"], "hydrolite_component": "graph_temporal_residual", "limitations": "Bidirectional modes are historical-analysis only.", "provenance": "DOI metadata only"},
    ]


def get_source(source_id: str) -> dict[str, Any]:
    return next(item for item in built_in_sources() if item["source_id"] == source_id)


def write_research_outputs(output_dir: str | Path = "output/research_methods") -> dict[str, Path]:
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    rows = built_in_sources()
    registry = root / "research_registry.xlsx"; licensing = root / "source_licensing_report.xlsx"; cards = root / "method_cards.xlsx"
    pd.DataFrame(rows).to_excel(registry, index=False)
    pd.DataFrame([{key: row[key] for key in ("source_id", "source_license", "code_available", "code_license", "implementation_mode", "provenance")} for row in rows] + [{"source_id": "ruiduobao/gee-dataset-intelligence-skill", "source_license": "license_file_missing", "code_available": True, "code_license": "license_file_missing", "implementation_mode": "method_inspired_clean_room", "provenance": "audited repository metadata only"}]).to_excel(licensing, index=False)
    pd.DataFrame([{ "method_id": row["source_id"], "title": row["title"], "borrowed_concepts": "; ".join(row["borrowed_concepts"]), "excluded_elements": "; ".join(row["excluded_elements"]), "notice": NOTICE, "limitations": row["limitations"]} for row in rows]).to_excel(cards, index=False)
    report_zh = root / "method_inspiration_report_zh.md"; report_en = root / "method_inspiration_report_en.md"
    body = "\n".join(f"- `{row['source_id']}`: {row['implementation_mode']}" for row in rows)
    report_zh.write_text(f"# HydroLite 水文环境方法借鉴实验室\n\n{NOTICE}\n\n{body}\n", encoding="utf-8")
    report_en.write_text(f"# HydroLite Method Inspiration Lab\n\n{NOTICE}\n\n{body}\n", encoding="utf-8")
    (root / "research_manifest.json").write_text(json.dumps({"notice": NOTICE, "sources": [row["source_id"] for row in rows], "third_party_skill": "license_file_missing"}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"registry": registry, "licensing": licensing, "cards": cards, "report_zh": report_zh, "report_en": report_en}
