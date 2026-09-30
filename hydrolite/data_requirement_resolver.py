"""Requirement-level acquisition decisions, separate from scientific readiness gates."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from hydrolite.connectors.contracts import DataRequirement, DatasetCandidate, PROJECT_TYPES
from hydrolite.connectors.registry import DataConnectorRegistry
from hydrolite.dataset_cache import safe_destination, atomic_json
from hydrolite.workspace import list_workspace_datasets, calculate_file_checksum

ALIASES = {"rainfall": "rainfall_observed", "observed_streamflow": "streamflow_observed", "forecast_rainfall": "rainfall_forecast", "continuous_meteorology": "daily_meteorology", "land_cover": "land_use"}
PUBLIC_TYPES = {"dem", "land_cover", "land_use", "vegetation_index", "rainfall", "temperature", "soil_moisture", "surface_water", "daily_meteorology"}
POINT_REQUESTS = {
    "DR01": ("coordinate_crs", "source_id", "longitude", "latitude", "crs", "coordinate_reference"),
    "DR02": ("outfall_actual_flow", "source_id", "value", "unit", "date_start", "date_end", "flow_kind"),
    "DR03": ("outfall_concentration", "source_id", "pollutant", "value", "unit", "date_start", "date_end", "measurement_role"),
    "DR04": ("receiving_water", "source_id", "receiving_water", "reach_id", "relation_evidence"),
    "DR05": ("wastewater_volume", "source_id", "value", "unit", "date_start", "date_end", "measurement_role"),
    "DR06": ("project_factor_approval", "factor_id", "reviewer", "applicability_evidence", "proposed_action"),
}
USER_REQUIRED_COLUMNS = ["requirement", "why_required", "currently_missing", "required_fields", "unit", "time_coverage", "spatial_coverage", "accepted_format", "template", "blocked_capability", "priority", "strategy", "action"]


def classify_requirement_source(requirement):
    if requirement.requires_project_measurement or requirement.data_type in PROJECT_TYPES:
        return "USER_REQUIRED"
    if requirement.data_type in {"emission_factors", "permits", "guidelines"}:
        return "AUTO_DISCOVER_REQUIRE_APPROVAL"
    return "AUTO_FETCH" if requirement.allow_auto_fetch else requirement.fallback_strategy


def _project_evidence_reason(requirement):
    reasons = {
        "coordinate_crs": "项目排口坐标和坐标系必须由项目测量/设计资料确认；公开底图不能证明具体排口位置。",
        "outfall_actual_flow": "排口实际流量是项目与时段特定的实测证据；公共设计规模或遥感不能替代。",
        "outfall_concentration": "污染物浓度必须来自对应排口、污染物和采样时段的检测记录。",
        "receiving_water": "真实受纳河段需要排水关系或现场证据确认；最近的公开水系线不能证明排放去向。",
        "wastewater_volume": "废水量需由该项目的计量/台账记录支持，不能从公共遥感数据推定。",
        "project_factor_approval": "项目适用系数需要责任人审查与适用性批准；发现公共参考不等于自动采用。",
    }
    return reasons.get(requirement.data_type, "该项是项目专属实测或决策证据，不能由通用公共数据代替。")


def rank_candidate(requirement, candidate):
    c, r = candidate, requirement
    checks = {}
    checks["variable_fit"] = c.data_type == r.data_type and (not r.variables or set(r.variables) <= set(c.variables))
    checks["spatial_coverage"] = not r.spatial_extent or bool(c.spatial_extent and c.spatial_extent[0] <= r.spatial_extent[0] and c.spatial_extent[1] <= r.spatial_extent[1] and c.spatial_extent[2] >= r.spatial_extent[2] and c.spatial_extent[3] >= r.spatial_extent[3])
    checks["temporal_coverage"] = not r.temporal_extent or bool(len(c.temporal_extent) == 2 and all(c.temporal_extent) and c.temporal_extent[0][:10] <= r.temporal_extent[0][:10] and c.temporal_extent[1][:10] >= r.temporal_extent[1][:10])
    checks["resolution"] = r.minimum_resolution is None or (c.resolution is not None and c.resolution <= r.minimum_resolution)
    checks["provider_authority"] = c.trusted_provider and (not r.acceptable_sources or c.provider in r.acceptable_sources)
    checks["license"] = c.license_status == "known"
    checks["missingness"] = c.metadata.get("missing_fraction", 1) <= r.quality_rules.get("max_missing_fraction", 0)
    max_age = r.quality_rules.get("max_age_days")
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(c.metadata.get("source_date", "").replace("Z", "+00:00"))).days
        checks["freshness"] = max_age is None or age <= max_age
    except (ValueError, TypeError):
        checks["freshness"] = max_age is None
    hard = [key for key in checks if key != "missingness"]
    # Missingness is verified after download, never invented from a search ranking.
    return {"score": sum(bool(value) for value in checks.values()), "quality": checks,
            "eligible": all(checks[key] for key in hard), "qc_pending": not checks["missingness"],
            "selection_reason": "All hard coverage/variable/license/provider constraints" if all(checks[key] for key in hard) else "Candidate requires review; hard constraints not all satisfied"}


def _local_matches(requirement, workspace):
    kind = ALIASES.get(requirement.data_type, requirement.data_type)
    rows = [item for item in list_workspace_datasets(workspace) if (item.get("user_declared_type") or item.get("dataset_type") or item.get("classification", {}).get("dataset_type")) == kind]
    ready = []
    root = Path(workspace).expanduser().resolve()
    for item in rows:
        relative = item.get("standardized_path") or item.get("processed_path")
        path = (root / relative).resolve() if relative else None
        if not path or root not in path.parents or not path.is_file() or item.get("quality_status") not in {"ready", "ready_with_warnings"}:
            continue
        if item.get("standardized_checksum") and calculate_file_checksum(path) != item["standardized_checksum"]:
            continue
        if requirement.requires_project_measurement or requirement.data_type in PROJECT_TYPES:
            if item.get("source_type") == "online_public" or not item.get("project_measurement_confirmed"):
                continue
        if requirement.required_fields and path.suffix == ".csv":
            if not set(requirement.required_fields) <= set(pd.read_csv(path, nrows=0).columns):
                continue
        if requirement.spatial_extent or requirement.temporal_extent:
            provenance = item.get("online_provenance", {})
            candidate_data = provenance.get("candidate")
            if not candidate_data or not rank_candidate(requirement, DatasetCandidate(**candidate_data))["eligible"]:
                continue
        ready.append(item["dataset_id"])
    return rows, ready


def resolve_requirement(requirement, workspace, registry=None, online=False):
    registry = registry or DataConnectorRegistry()
    strategy = classify_requirement_source(requirement)
    local, ready = _local_matches(requirement, workspace)
    result = {"requirement": requirement.as_dict(), "strategy": strategy, "local_dataset_ids": ready, "candidates": [], "searches": []}
    if ready:
        cached_online = not online and any(
            item.get("dataset_id") in ready and item.get("source_type") == "online_public"
            for item in list_workspace_datasets(workspace)
        )
        return {**result, "status": "offline_cached" if cached_online else "local_ready",
                "reason": "Verified standardized dataset is available offline with recorded public-source provenance" if cached_online else "Verified local standardized data and QC"}
    if strategy == "USER_REQUIRED":
        if requirement.requires_project_measurement or requirement.data_type in PROJECT_TYPES:
            return {**result, "status": "project_measurement_required", "reason": _project_evidence_reason(requirement), "local_unreviewed_count": len(local)}
        supported = {value for values in registry.capabilities().values() for value in values}
        status = "unavailable" if requirement.data_type in supported or requirement.data_type in PUBLIC_TYPES else "unsupported"
        return {**result, "status": status, "reason": "No configured trusted public source; user-provided data may be uploaded", "local_unreviewed_count": len(local)}
    recommendations = registry.recommend(requirement, {"online": online})
    result.update(recommendations)
    eligible = [row for row in result["candidates"] if row["eligible"] and row["candidate"]["access_status"] == "public_download"]
    if strategy == "AUTO_DISCOVER_REQUIRE_APPROVAL":
        status = "approval_required" if result["candidates"] else "unavailable"
    elif eligible:
        status = "auto_fetch_available"
    elif any(item.get("status") in {"dns_failure", "non_public_resolution", "proxy_blocked", "tls_failure", "remote_unavailable"} for item in result["searches"]):
        status = "network_blocked"
    elif local:
        status = "local_needs_qc"
    elif result["candidates"]:
        status = "online_candidate_available"
    else:
        supported = {value for values in registry.capabilities().values() for value in values}
        status = "unavailable" if requirement.data_type in supported or requirement.data_type in PUBLIC_TYPES else "unsupported"
    reason = "Acquisition is not QC readiness; candidate metadata never substitutes for project measurements"
    if status == "network_blocked":
        blocked = next(item["status"] for item in result["searches"] if item.get("status") in {"dns_failure", "non_public_resolution", "proxy_blocked", "tls_failure", "remote_unavailable"})
        reason = {
            "dns_failure": "数据源域名解析失败；请检查网络或 DNS resolver 设置。",
            "non_public_resolution": "数据源当前解析到非公网网络地址，为保护本机安全，HydroLite 已阻止连接。",
            "proxy_blocked": "当前 HTTPS 代理未能建立安全的数据源连接。",
            "tls_failure": "数据源 TLS 证书校验失败；HydroLite 未绕过凭证或证书检查。",
            "remote_unavailable": "公开数据源未能在限定请求时间内响应。",
        }[blocked]
    return {**result, "status": status, "reason": reason}


def requirements_for_scenario(scenario, context=None):
    context = context or {}
    if scenario == "water_environment_source_accounting":
        rows = [DataRequirement(key, values[0], required_fields=values[1:] + ("document_reference",), requires_project_measurement=True) for key, values in POINT_REQUESTS.items()]
        rows.append(DataRequirement("public_factor_references", "emission_factors", required=False, preferred_connectors=("regulatory",), fallback_strategy="AUTO_DISCOVER_REQUIRE_APPROVAL"))
        return rows
    if scenario in {"SC10", "gee_data_discovery"}:
        kinds = [(name, False) for name in ("dem", "land_cover", "vegetation_index", "rainfall", "temperature", "soil_moisture", "surface_water")]
    elif scenario.startswith("SC"):
        from hydrolite.scenario_registry import get_scenario
        definition = get_scenario(scenario)
        kinds = [(name, True) for name in definition.required_data] + [(name, False) for name in definition.optional_data]
    else:
        from hydrolite.data_requirements import list_model_data_requirements
        if scenario == "full_modeling_workflow":
            models = list(__import__("hydrolite.data_requirements", fromlist=["_MODEL_REQUIREMENTS"])._MODEL_REQUIREMENTS)
            kinds = list(dict.fromkeys((item["dataset_type"], item["required"]) for model in models for item in list_model_data_requirements(model)))
            return [DataRequirement(name, name, required=required, allow_auto_fetch=name in PUBLIC_TYPES,
                                    fallback_strategy="AUTO_FETCH" if name in PUBLIC_TYPES else "USER_REQUIRED") for name, required in kinds]
        aliases = {"watershed_hydrology": "hydrolite_event_model", "drought": "drought_monitoring"}
        kinds = [(item["dataset_type"], item["required"]) for item in list_model_data_requirements(aliases.get(scenario, scenario))]
        if not kinds:
            raise ValueError("Unsupported scenario requirements")
    return [DataRequirement(name, name, required=required,
                            spatial_extent=tuple(context.get("bbox", [])), temporal_extent=tuple(context.get("dates", [])),
                            minimum_resolution=context.get("maximum_resolution_m"), allow_auto_fetch=name in PUBLIC_TYPES,
                            fallback_strategy="AUTO_FETCH" if name in PUBLIC_TYPES else "USER_REQUIRED")
            for name, required in kinds]


def resolve_scenario_requirements(scenario, workspace, registry=None, online=False, context=None, requirements=None):
    specs = requirements if requirements is not None else requirements_for_scenario(scenario, context)
    rows = [resolve_requirement(row, workspace, registry, online) for row in specs]
    count = len(rows)
    automatic = sum(row["status"] == "auto_fetch_available" for row in rows)
    candidates = sum(row["status"] in {"approval_required", "online_candidate_available"} for row in rows)
    user = sum(row["strategy"] == "USER_REQUIRED" and row["status"] != "local_ready" for row in rows)
    ready_statuses = {"local_ready", "offline_cached"}
    blocked = [row["requirement"]["requirement_id"] for row in rows if row["requirement"]["required"] and row["status"] not in ready_statuses and not row["requirement"]["quality_rules"].get("allow_missing_warning", False)]
    local_ready = sum(row["status"] in ready_statuses for row in rows)
    return {"scenario": scenario, "requirements": rows, "required_blockers": blocked, "run_gate": "blocked" if blocked else "ready_with_warnings", "metrics": {"requirements_evaluated": count, "local_ready": local_ready, "auto_fetch": automatic, "online_candidate": candidates, "user_required": user, "unavailable": sum(row["status"] == "unavailable" for row in rows), "network_blocked": sum(row["status"] == "network_blocked" for row in rows), "automatic_data_resolution_rate": (local_ready + automatic) / count if count else 0, "auto_fetch_rate": automatic / count if count else 0, "online_candidate_resolution_rate": candidates / count if count else 0, "user_required_rate": user / count if count else 0}, "interpretation": "Rates count requirements, not files. Automatic resolution rate counts QC-ready local/cached requirements plus fetch-eligible requirements; candidate discovery alone is not resolution, and fetch availability is not scientific readiness."}


def build_user_required_data_list(resolution):
    rows = []
    for row in resolution["requirements"]:
        if row["status"] not in {"project_measurement_required", "unavailable", "unsupported"}:
            continue
        req = row["requirement"]
        rows.append({"requirement": req["requirement_id"], "why_required": row["reason"], "currently_missing": req["data_type"], "required_fields": ";".join(req["required_fields"]), "unit": req["quality_rules"].get("unit", "explicit source units"), "time_coverage": req["temporal_extent"], "spatial_coverage": req["spatial_extent"], "accepted_format": "CSV/XLSX with provenance", "template": req["requirement_id"] + ".csv", "blocked_capability": resolution["scenario"], "priority": "P0" if req["required"] else "optional", "strategy": row["strategy"], "action": "review_candidate" if row["candidates"] else "provide_or_configure_source"})
    return rows


def explain_requirement_resolution(resolution):
    return "\n".join(f"- {row['requirement']['requirement_id']}: {row['strategy']} / {row['status']} — {row['reason']}" for row in resolution["requirements"])


def write_resolution(resolution, output):
    output = safe_destination(output)
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / "resolution_manifest.json", resolution)
    missing = build_user_required_data_list(resolution)
    pd.DataFrame(missing, columns=USER_REQUIRED_COLUMNS).to_excel(output / "user_required_data.xlsx", index=False)
    for row in missing:
        # Generated template names cannot be supplied as paths.
        from hydrolite.runtime_paths import sanitize_runtime_identifier
        name = sanitize_runtime_identifier(row["requirement"])
        columns = row["required_fields"].split(";") if row["required_fields"] else ["timestamp", "value", "unit", "source_reference"]
        folder = output / "templates"
        folder.mkdir(exist_ok=True)
        pd.DataFrame(columns=columns).to_csv(folder / (name + ".csv"), index=False)
    (output / "data_acquisition_readiness_report_zh.md").write_text("# 数据获取与就绪度\n\n公开数据不冒充项目实测；下载成功不等于模型就绪。\n\n" + explain_requirement_resolution(resolution) + "\n\n" + json.dumps(resolution["metrics"], ensure_ascii=False, indent=2), encoding="utf-8")
    return output / "resolution_manifest.json"


def fetch_recommended(resolution, workspace, registry=None, cache=None, requirement_id=None, confirm_large=False):
    from hydrolite.data_acquisition import import_fetched_dataset
    registry = registry or DataConnectorRegistry()
    results = []
    for row in resolution["requirements"]:
        if requirement_id and row["requirement"]["requirement_id"] != requirement_id:
            continue
        # Recompute eligibility from contract, not editable manifest status fields.
        requirement = DataRequirement(**row["requirement"])
        if classify_requirement_source(requirement) != "AUTO_FETCH":
            results.append({"requirement_id": requirement.requirement_id, "status": "approval_required"})
            continue
        eligible = [item for item in row["candidates"] if rank_candidate(requirement, DatasetCandidate(**item["candidate"]))["eligible"] and item["candidate"]["access_status"] == "public_download"]
        if not eligible:
            continue
        if len(eligible) > 1 and eligible[0]["score"] == eligible[1]["score"]:
            results.append({"requirement_id": requirement.requirement_id, "status": "candidate_selection_required"})
            continue
        result = registry.fetch(eligible[0]["candidate"], cache=cache, confirm_large=confirm_large)
        if result.get("checksum"):
            result["data_center"] = import_fetched_dataset(result, workspace, requirement)
        results.append({"requirement_id": requirement.requirement_id, **result})
    return results


def resolve_point_source_requests(workspace, m9a2_dir, output, online=False):
    """Read the six audited packages only. Never rescan historical project documents."""
    specs = requirements_for_scenario("water_environment_source_accounting")
    # A project workspace's assigned type list can be stale; the six M9A.2
    # packages remain the authoritative request contract for this review.
    result = resolve_scenario_requirements("water_environment_source_accounting", workspace, online=online, requirements=specs)
    root = Path(m9a2_dir)
    def package_file(name, legacy_subdir):
        candidates = (root / legacy_subdir / name, root / name)
        path = next((item for item in candidates if item.is_file()), None)
        if path is None:
            raise FileNotFoundError(f"M9A.2 package is missing: {name}")
        return path

    manifest = json.loads(package_file("m9a2_manifest.json", "reports").read_text())
    requests = pd.read_excel(package_file("m9a2_project_data_request_pack.xlsx", "requests")).fillna("")
    names = {row["request_id"]: row for row in requests.to_dict("records")}
    for row in result["requirements"]:
        row["existing_request"] = names.get(row["requirement"]["requirement_id"], {})
    # Reviewed public references are candidates, not new discovery or approved coefficients.
    factor_path = root / "factors/factor_decision_pack.xlsx"
    factors = factor_path if factor_path.is_file() else root / "factor_decision_pack.xlsx"
    frame = pd.read_excel(factors).fillna("") if factors.exists() else pd.DataFrame()
    public = next(row for row in result["requirements"] if row["requirement"]["data_type"] == "emission_factors")
    if not frame.empty:
        public.update(status="approval_required", candidates=[{"candidate": {"dataset_id": str(row.get("factor_id") or row.get("source_reference") or f"public_factor_{i}"), "connector_id": "regulatory", "provider": str(row.get("source_name") or row.get("source_reference") or "M9A.2 reviewed public reference"), "data_type": "emission_factors", "source_url": str(row.get("source_url") or ""), "version": "", "variables": (str(row.get("pollutant") or ""),), "spatial_extent": (), "temporal_extent": (), "resolution": None, "crs": None, "nodata": None, "license": str(row.get("license") or "unknown"), "license_status": str(row.get("license_status") or "unknown"), "trusted_provider": True, "access_status": "approval_required", "estimated_size": None, "content_type": "", "checksum": "", "metadata": {"source_reference": str(row.get("source_reference") or ""), "existing_m9a2_candidate": True}}, "score": 0, "quality": {}, "eligible": False, "qc_pending": True, "selection_reason": "Existing public reference; project applicability requires human approval"} for i, row in enumerate(frame.to_dict("records"))], reason="Existing M9A.2 public references reused; applicability remains unapproved", existing_candidate_count=len(frame))
        result["metrics"].update(online_candidate=1, online_candidate_resolution_rate=1 / len(result["requirements"]), unavailable=0)
    result["m9a2_gates_unchanged"] = manifest["gates"]
    write_resolution(result, output)
    table = [{"requirement": row["requirement"]["requirement_id"], "data_type": row["requirement"]["data_type"], "strategy": row["strategy"], "status": row["status"], "connector_can_resolve": row["status"] == "auto_fetch_available", "reason": row["reason"]} for row in result["requirements"]]
    pd.DataFrame(table).to_excel(Path(output) / "gaoqiao_data_resolution_report.xlsx", index=False)
    return result
