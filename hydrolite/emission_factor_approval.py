"""Project decisions are separate from publication authority and stage semantics."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import math

from hydrolite.water_environment_contracts import EmissionFactor, Record

APPROVAL_STATES = {"candidate", "reviewed", "approved_for_project", "rejected", "superseded"}
REQUIRED_METADATA = {"title", "issuer", "year", "original_unit", "normalized_unit", "method", "reference", "retrieval_date", "applicability", "limitations"}


@dataclass(frozen=True, slots=True)
class EmissionFactorApproval(Record):
    factor_id: str
    project_id: str
    status: str
    actor: str
    comment: str
    timestamp: str
    factor_checksum: str


@dataclass(frozen=True, slots=True)
class ProjectEmissionFactorSet(Record):
    factor_set_id: str
    project_id: str
    created_at: str
    factors: tuple[dict, ...]
    approvals: tuple[dict, ...]
    unresolved_categories: tuple[str, ...]
    checksum: str


def factor_checksum(factor: EmissionFactor) -> str:
    return sha256(json.dumps(factor.as_dict(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def factor_stage(factor: EmissionFactor) -> str:
    text = " ".join([factor.notes, str(factor.evidence.get("method", "")), str(factor.evidence.get("title", ""))]).lower()
    if any(term in text for term in ("入河系数", "delivery coefficient", "delivery ratio")): return "delivery_factor"
    if any(term in text for term in ("流失量", "输出系数", "径流流失系数", "流失系数", "export coefficient", "runoff loss")): return "export_factor"
    return factor.factor_stage


def approve_factor(factor: EmissionFactor, project_id: str, status: str, *, actor: str, comment: str) -> EmissionFactorApproval:
    from hydrolite.emission_factor_registry import validate_emission_factor
    if status not in APPROVAL_STATES or not project_id or not actor.strip() or not comment.strip(): raise ValueError("Project, approval state, actor and comment required")
    if status == "approved_for_project":
        if factor.example: raise ValueError("Example factors cannot be approved")
        if factor_stage(factor) != "generation_factor": raise ValueError("Export/delivery factors cannot enter generated load")
        if factor.value is None or not math.isfinite(factor.value): raise ValueError("Verified factor value required")
        if validate_emission_factor(factor)["status"] != "passed": raise ValueError("Invalid factor")
        missing = [key for key in REQUIRED_METADATA if not factor.evidence.get(key)]
        if missing: raise ValueError("Factor evidence missing: " + ", ".join(sorted(missing)))
    return EmissionFactorApproval(factor.factor_id, project_id, status, actor, comment, datetime.now(timezone.utc).isoformat(), factor_checksum(factor))


def approved_project_factors(factors: list[EmissionFactor], approvals: list[EmissionFactorApproval], project_id: str) -> list[EmissionFactor]:
    latest = {a.factor_id: a for a in approvals if a.project_id == project_id}
    result = []
    for factor in factors:
        decision = latest.get(factor.factor_id)
        if decision and decision.status == "approved_for_project" and decision.factor_checksum == factor_checksum(factor):
            approve_factor(factor, project_id, decision.status, actor=decision.actor, comment=decision.comment)
            result.append(replace(factor, approved_for_real_project=True))
    return result


def build_project_factor_set(project_id: str, factors: list[EmissionFactor], approvals: list[EmissionFactorApproval], unresolved: list[str]) -> ProjectEmissionFactorSet:
    approved = approved_project_factors(factors, approvals, project_id)
    content = {"project_id": project_id, "factors": [f.as_dict() for f in approved], "approvals": [a.as_dict() for a in approvals], "unresolved_categories": sorted(unresolved)}
    checksum = sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return ProjectEmissionFactorSet("factor_set_" + checksum[:16], project_id, datetime.now(timezone.utc).isoformat(), tuple(content["factors"]), tuple(content["approvals"]), tuple(content["unresolved_categories"]), checksum)


def load_verified_candidates(path):
    from pathlib import Path
    import yaml
    sources = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["sources"]
    factors = []
    for source in sources:
        for row in source["values"]:
            for pollutant in ("NH3-N", "TN", "TP"):
                factors.append(EmissionFactor(factor_id=f"{source['id']}:{row['region']}:{pollutant}", source_type="rural_domestic", pollutant=pollutant, value=row[pollutant] / 1000, numerator_unit="kg/day", denominator_unit="person", temporal_basis="daily", region_applicability=row["region"], source_reference=source["reference"], source_type_reference=source["source_type_reference"], confidence="medium", uncertainty_low=None, uncertainty_high=None, valid_from="", valid_to="", notes=source["limitations"], evidence={k: v for k, v in source.items() if k != "values"}))
    return factors, [{k: v for k, v in s.items() if k != "values"} for s in sources]
