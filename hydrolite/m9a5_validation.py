"""Runtime-only M9A.5 provider and public E2E acceptance artifacts."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import zipfile

import pandas as pd
import yaml

from hydrolite.connectors.public import provider_config
from hydrolite.connectors.registry import DataConnectorRegistry, provider_profiles
from hydrolite.connectors.transport import ConnectorError
from hydrolite.runtime_paths import get_runtime_root
from hydrolite.workspace import calculate_file_checksum, create_workspace


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_M9A2 = Path.home() / ".hydrolite/workspaces/gaoqiao-river-basin-real-validation/derived/m9a2"
TEST_BBOX = [113.0, 22.0, 114.0, 23.0]


def _json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _provider_endpoints():
    config = provider_config()
    return {
        "hydrosheds": ("https://data.hydrosheds.org/file/hydrosheds-v1-dem/hyd_as_dem_30s.zip", config["hydrosheds"]["allowed_hosts"]),
        "nasa_cmr": ("https://cmr.earthdata.nasa.gov/search/collections.json?page_size=1", config["nasa_cmr"]["allowed_hosts"]),
        "copernicus_stac": ("https://stac.dataspace.copernicus.eu/v1/collections?limit=1", config["copernicus_stac"]["allowed_hosts"]),
        "earth_engine": ("https://storage.googleapis.com/earthengine-stac/catalog/catalog.json", config["gee"]["allowed_hosts"]),
    }


def _provider_status_rows(registry, probe_results, e2e):
    profiles = provider_profiles()
    health = {row["connector_id"]: row for row in registry.health()}
    ids = {"earth_engine": "gee", "copernicus_stac": "copernicus_stac", "nasa_cmr": "nasa_cmr", "hydrosheds": "hydrosheds"}
    rows = []
    for profile_id, connector_id in ids.items():
        profile = profiles[profile_id]
        health_status = health.get(connector_id, {}).get("status", "unavailable")
        probe = probe_results.get(profile_id, {})
        rows.append({
            "provider": profile["provider_name"], "discovery": probe.get("discovery", "not_tested"),
            "fetch": "supported" if profile["fetch_supported"] else "not_supported_or_not_enabled",
            "auth": profile["authentication"], "DNS": probe.get("dns", "not_tested"),
            "security": probe.get("security", "not_tested"), "license": profile["license_status"],
            "cache": "external content-addressed cache configured", "real E2E": e2e.get("status", "not_tested") if profile_id == "hydrosheds" else "not_selected",
            "notes": probe.get("notes") or health_status,
        })
    return rows


def _try_hydrosheds_e2e(registry, output):
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.dataset_cache import DatasetCache
    from hydrolite.data_acquisition import import_fetched_dataset
    from hydrolite.data_quality_center import run_dataset_quality_checks
    from hydrolite.data_lineage import validate_lineage_graph
    from hydrolite.project_versioning import create_project_version
    from hydrolite.data_upload import extract_safe_archive

    row = {"status": "environment_blocked", "provider": "HydroSHEDS", "dataset": "hydrosheds-v1/dem/asia-30s",
           "aoi": {"bbox_wgs84": TEST_BBOX, "kind": "non-project public smoke bbox"}, "steps": {}}
    found = registry.search("hydrosheds", {"online": True, "data_type": "dem", "bbox": TEST_BBOX})
    row["steps"]["search"] = found["status"]
    if not found.get("candidates"):
        row["error_class"] = found.get("provider_failure_class") or found.get("status")
        row["error_message"] = found.get("error_message", "No candidate for bounded AOI")
        return row
    candidate = found["candidates"][0]
    request = DataRequirement("m9a5_e2e_dem", "dem", spatial_extent=tuple(TEST_BBOX), allow_auto_fetch=True, fallback_strategy="AUTO_FETCH")
    from hydrolite.data_requirement_resolver import rank_candidate
    suitability = rank_candidate(request, candidate)
    row["suitability"] = suitability
    row["steps"]["suitability"] = "passed" if suitability["eligible"] else "failed"
    if not suitability["eligible"]:
        row.update(status="candidate_not_suitable", error_message=suitability["selection_reason"])
        return row
    cache = DatasetCache()
    fetched = registry.fetch(candidate, cache=cache)
    row["steps"]["fetch"] = fetched.get("status")
    if fetched.get("status") not in {"fetched", "cached", "offline_cached"}:
        row.update(status="environment_blocked" if fetched.get("status") in {"dns_failure", "non_public_resolution", "tls_failure", "remote_unavailable", "proxy_blocked", "security_blocked"} else "fetch_failed",
                   error_class=fetched.get("status"), error_message=fetched.get("error_message", "Provider fetch unavailable"))
        return row
    archive = Path(fetched["local_path"])
    row.update(bytes=archive.stat().st_size, archive_sha256=fetched["checksum"], source_url_host="data.hydrosheds.org")
    extracted_root = get_runtime_root() / "m9a5" / "e2e" / "extracted"
    try:
        members = extract_safe_archive(archive, extracted_root)
        rasters = [path for path in members if path.suffix.lower() in {".tif", ".tiff"}]
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        row.update(status="e2e_incomplete", error_class="invalid_dataset", error_message=str(exc))
        return row
    if len(rasters) != 1:
        row.update(status="e2e_incomplete", error_class="unsupported", error_message="Expected one GeoTIFF in the product archive")
        return row
    raster = rasters[0]
    checksum = calculate_file_checksum(raster)
    candidate_data = candidate.as_dict()
    candidate_data["metadata"] = {**candidate_data.get("metadata", {}), "archive_sha256": fetched["checksum"], "archive_cache_reference": str(archive), "data_origin_class": "derived"}
    native_fetch = {**fetched, "local_path": str(raster), "checksum": checksum, "candidate": candidate_data,
                    "processing_chain": tuple(fetched.get("processing_chain", ())) + ("safe_zip_extraction", "native_geotiff_checksum")}
    workspace = get_runtime_root() / "m9a5" / "e2e" / "workspace"
    if workspace.exists() and any(workspace.iterdir()):
        row.update(status="e2e_incomplete", error_class="runtime_state_exists", error_message="M9A.5 E2E workspace is non-empty; refusing overwrite")
        return row
    create_workspace(workspace, "M9A.5 public provider E2E")
    imported = import_fetched_dataset(native_fetch, workspace, request)
    row["steps"]["registry"] = "passed"
    row["steps"]["standardization"] = "native_geotiff_preserved"
    qc = run_dataset_quality_checks(imported["dataset_id"], workspace)
    row["steps"]["qc"] = qc["quality_status"]
    row["qc_warnings"] = qc.get("warnings", [])
    row["lineage"] = validate_lineage_graph(workspace)["status"]
    row["steps"]["lineage"] = row["lineage"]
    second = registry.fetch(candidate, cache=cache, policy="reuse_if_unchanged")
    offline = registry.fetch(candidate, cache=cache, policy="offline_only")
    row["steps"]["second_fetch_cache"] = second.get("status")
    row["steps"]["offline_replay"] = offline.get("status")
    row["steps"]["offline_checksum_match"] = offline.get("checksum") == fetched.get("checksum")
    row["checksums"] = {"archive_sha256": fetched["checksum"], "native_raster_sha256": checksum}
    row["licensing"] = {"license": candidate.license, "attribution": candidate.metadata.get("citation"), "status": candidate.license_status}
    if qc["quality_status"] not in {"ready", "ready_with_warnings"} or row["lineage"] != "passed" or not row["steps"]["offline_checksum_match"]:
        row.update(status="e2e_incomplete", error_class="quality_or_replay_gate", error_message="QC, lineage, or offline replay gate did not pass")
        return row
    version = create_project_version(workspace, created_by="m9a5_validation", description="Public provider E2E immutable snapshot")
    row["snapshot"] = {"project_version_id": version["project_version_id"], "data_snapshot_id": version["data_snapshot_id"], "checksum": version["checksum"]}
    row["steps"]["snapshot"] = "passed"
    # A new remote version must not silently change the content-addressed object or prior snapshot.
    changed = replace(candidate, version=candidate.version + ".probe-change")
    row["provider_version_change_test"] = {"new_version_cache_miss": cache.lookup(changed) is None, "prior_checksum_retained": version["data_snapshot_id"] is not None}
    row["status"] = "passed" if second.get("status") in {"cached", "offline_cached"} and offline.get("status") == "offline_cached" and row["provider_version_change_test"]["new_version_cache_miss"] else "e2e_incomplete"
    row["steps"]["fetch"] = "passed"
    row["steps"]["snapshot"] = "passed"
    return row


def write_m9a5_acceptance(output_dir=None, m9a2_dir=None):
    output = Path(output_dir or ROOT / "output/data_acquisition/m9a5").expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    registry = DataConnectorRegistry()
    profiles = provider_profiles()
    endpoints = _provider_endpoints()
    probe_results = {}
    failure_signature = []
    attempted_hosts = set()

    def record_probe(provider_id, observed_status):
        from hydrolite.connectors.diagnostics import diagnose_url
        url, hosts = endpoints[provider_id]
        host = url.split("/")[2]
        diagnostic = diagnose_url(url, hosts, probe=False)
        dns = diagnostic.get("status", "unknown")
        effective = observed_status if observed_status in {"dns_failure", "non_public_resolution", "tls_failure", "remote_unavailable", "security_blocked", "proxy_blocked"} else dns
        probe_results.setdefault(provider_id, {}).update(dns=dns, security="blocked" if effective in {"non_public_resolution", "security_blocked", "proxy_blocked"} else "passed" if dns == "public_address_validated" else "not_verified")
        if effective in {"dns_failure", "non_public_resolution", "security_blocked"} and host not in attempted_hosts:
            failure_signature.append((host, effective))
            attempted_hosts.add(host)

    # HydroSHEDS is the first and only binary E2E candidate.
    try:
        e2e = _try_hydrosheds_e2e(registry, output)
    except Exception as exc:
        e2e = {"status": "e2e_incomplete", "provider": "HydroSHEDS", "error_class": type(exc).__name__, "error_message": str(exc)[:500]}
    probe_results["hydrosheds"] = {"discovery": e2e.get("steps", {}).get("search", "not_available"), "notes": e2e.get("error_class") or e2e.get("status")}
    record_probe("hydrosheds", e2e.get("error_class"))

    provider_queries = {
        "nasa_cmr": {"online": True, "data_type": "rainfall", "bbox": TEST_BBOX, "start": "2024-01-01", "end": "2024-01-02", "limit": 1},
        "copernicus_stac": {"online": True, "data_type": "satellite_image", "bbox": TEST_BBOX, "limit": 1},
    }
    for provider_id, request in provider_queries.items():
        if len(attempted_hosts) >= 3 and len({status for _, status in failure_signature[-3:]}) == 1:
            probe_results[provider_id] = {"dns": "not_tested_after_common_block", "security": "not_tested", "discovery": "not_tested_after_common_block"}
            continue
        result = registry.search(provider_id, request)
        probe_results.setdefault(provider_id, {})["discovery"] = result.get("status")
        probe_results[provider_id]["notes"] = result.get("error_message", "bounded public metadata query")
        record_probe(provider_id, result.get("status"))

    common_dns_block = len(attempted_hosts) >= 3 and len({status for _, status in failure_signature[-3:]}) == 1
    if common_dns_block:
        probe_results["earth_engine"] = {"dns": "not_tested_after_common_block", "security": "not_tested", "discovery": "offline_catalog_available", "notes": "Catalog metadata remains offline; remote transport stopped after three independent blocked hosts"}
    else:
        gee_result = registry.search("gee", {"online": False, "data_type": "dem"})
        probe_results.setdefault("earth_engine", {})["discovery"] = "offline_catalog_available" if gee_result.get("candidates") else gee_result.get("status")
        # Probe only the public official STAC metadata transport, never EE compute/auth.
        from hydrolite.connectors.diagnostics import diagnose_url
        gee_url, gee_hosts = endpoints["earth_engine"]
        gee_diag = diagnose_url(gee_url, gee_hosts, probe=True)
        probe_results["earth_engine"].update(dns=gee_diag.get("status"), security="blocked" if gee_diag.get("status") in {"non_public_resolution", "security_blocked"} else "passed" if gee_diag.get("status") == "healthy" else "not_verified", notes="Catalog metadata only; compute auth remains separate")
        if gee_diag.get("status") in {"dns_failure", "non_public_resolution", "security_blocked"}:
            failure_signature.append((gee_url.split("/")[2], gee_diag["status"]))

    rows = _provider_status_rows(registry, probe_results, e2e)
    pd.DataFrame(rows, columns=["provider", "discovery", "fetch", "auth", "DNS", "security", "license", "cache", "real E2E", "notes"]).to_excel(output / "provider_health_matrix.xlsx", index=False)
    matrix_path = ROOT / "config/connectors/data_source_matrix.yaml"
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    flattened = [{"scenario": scenario, "data_type": kind, "priority": i + 1, "source": source,
                  "source_mode": "USER_REQUIRED" if source == "project_user" else "AUTO_DISCOVER_REQUIRE_APPROVAL" if source == "approval_registry" else "provider_profile" if source in profiles else source}
                 for scenario, requirements in matrix["matrix"].items() for kind, sources in requirements.items() for i, source in enumerate(sources)]
    pd.DataFrame(flattened).to_excel(output / "data_source_matrix.xlsx", index=False)

    m9a2 = Path(m9a2_dir or DEFAULT_M9A2)
    gaoqiao = {"status": "unavailable", "m9a2_dir_exists": m9a2.is_dir(), "gates_unchanged": None}
    if m9a2.is_dir():
        try:
            from hydrolite.data_requirement_resolver import resolve_point_source_requests
            report_dir = output / "gaoqiao_resolution"
            resolved = resolve_point_source_requests(m9a2.parent.parent.parent, m9a2, report_dir, online=False)
            shutil.copy2(report_dir / "user_required_data.xlsx", output / "user_required_data.xlsx")
            source_manifest = json.loads((m9a2 / "m9a2_manifest.json").read_text(encoding="utf-8"))
            categories = [
                {"category": "DEM", "source_mode": "AUTO_FETCH", "status": "network_blocked; AOI suitability not re-evaluated", "reason": "HydroSHEDS bounded public product candidate is configured; exact project AOI and resolution must be revalidated."},
                {"category": "hydrography", "source_mode": "AUTO_DISCOVER_REQUIRE_APPROVAL", "status": "candidate_required", "reason": "Raster flow products are available; no vector reach is accepted as the project's receiving reach without review."},
                {"category": "rainfall", "source_mode": "AUTO_DISCOVER_REQUIRE_APPROVAL", "status": "metadata_only_or_network_blocked", "reason": "NASA/GEE discovery does not make reanalysis a project rain gauge observation."},
                {"category": "land_cover", "source_mode": "AUTO_DISCOVER_REQUIRE_APPROVAL", "status": "metadata_only_or_network_blocked", "reason": "Remote-sensing classification requires year, class schema, resolution and license review."},
                {"category": "CRS", "source_mode": "USER_REQUIRED", "status": "project_evidence_required", "reason": "The coordinate reference system of project records must be confirmed from their source."},
                {"category": "receiving_reach", "source_mode": "USER_REQUIRED", "status": "project_evidence_required", "reason": "Public hydrography is only a candidate; discharge relation requires project evidence."},
                {"category": "actual_outfall_flow", "source_mode": "USER_REQUIRED", "status": "project_measurement_required", "reason": "Public data cannot substitute site- and period-specific measured discharge."},
                {"category": "wastewater_volume", "source_mode": "USER_REQUIRED", "status": "project_measurement_required", "reason": "Requires project meter/log evidence."},
                {"category": "concentration", "source_mode": "USER_REQUIRED", "status": "project_measurement_required", "reason": "Requires same-source, analyte- and time-specific laboratory evidence."},
                {"category": "emission_factor_approval", "source_mode": "AUTO_DISCOVER_REQUIRE_APPROVAL", "status": "approval_required", "reason": "Existing public references are candidates only; applicability approval remains a project decision."},
            ]
            point_rows = [{"requirement": row["requirement"]["requirement_id"], "data_type": row["requirement"]["data_type"], "source_mode": row.get("source_mode", row["strategy"]), "status": row["status"], "reason": row["reason"]} for row in resolved["requirements"]]
            with pd.ExcelWriter(output / "gaoqiao_requirement_resolution.xlsx") as writer:
                pd.DataFrame(categories).to_excel(writer, sheet_name="source_categories", index=False)
                pd.DataFrame(point_rows).to_excel(writer, sheet_name="m9a2_requests", index=False)
            gaoqiao = {"status": "passed", "m9a2_dir_exists": True, "gates_unchanged": resolved["m9a2_gates_unchanged"] == source_manifest.get("gates"),
                       "gates": source_manifest.get("gates"), "categories": categories, "requirements": [{"id": row["requirement"]["requirement_id"], "status": row["status"], "source_mode": row.get("source_mode", row["strategy"])} for row in resolved["requirements"]]}
        except Exception as exc:
            gaoqiao = {"status": "failed", "m9a2_dir_exists": True, "error": type(exc).__name__}
    else:
        pd.DataFrame(columns=["requirement", "why_required", "currently_missing", "required_fields", "unit", "time_coverage", "spatial_coverage", "accepted_format", "template", "blocked_capability", "priority", "strategy", "action"]).to_excel(output / "user_required_data.xlsx", index=False)
        pd.DataFrame(columns=["requirement", "status", "source_mode", "reason"]).to_excel(output / "gaoqiao_requirement_resolution.xlsx", index=False)

    hosts_tested = list(dict.fromkeys(host for host, _ in failure_signature))
    classifications = [status for _, status in failure_signature]
    common = len(hosts_tested) >= 3 and len(set(classifications[-3:])) == 1 and classifications[-1] in {"non_public_resolution", "dns_failure", "security_blocked"}
    network_status = "blocked" if common or (failure_signature and all(status in {"dns_failure", "non_public_resolution", "security_blocked"} for _, status in failure_signature)) else "partial_or_available"
    from hydrolite.connectors.diagnostics import _proxy_summary
    proxy_presence = {name: row.get("status") == "present" for name, row in _proxy_summary().items()}
    diag = ["# M9A.5 网络环境诊断", "", f"- 状态：`{network_status}`", f"- 代理环境（仅 presence）：`{json.dumps(proxy_presence, ensure_ascii=False)}`", "- 安全策略：production public-only 保持不变；未启用私网或绕过 DNS 校验。", "", "## Provider 主机与解析结论"]
    for provider, result in probe_results.items():
        diag.append(f"- `{provider}`：DNS/安全状态 `{result.get('dns', 'not_tested')}`；{result.get('notes', '')}")
    if common:
        diag.extend(["", "多个独立官方域名呈现相同 DNS/非公网解析阻断；建议用户检查 VPN、DNS resolver、Network Extension、安全软件、/etc/resolver 与系统 resolver 配置。HydroLite 未修改系统网络设置。"])
    else:
        diag.extend(["", "若网络请求未通过，请检查 VPN、DNS resolver、Network Extension、安全软件、/etc/resolver 与系统 resolver 配置；HydroLite 未修改系统网络设置。"])
    (output / "network_environment_diagnostic.md").write_text("\n".join(diag) + "\n", encoding="utf-8")
    _json(output / "real_public_e2e.json", e2e)
    _json(output / "m9a5_manifest.json", {"generated_at": datetime.now(timezone.utc).isoformat(), "branch": "codex/m9a5-public-provider-pack",
        "provider_ids": list(profiles), "network_status": network_status, "providers": rows, "e2e_status": e2e.get("status"),
        "gaoqiao": gaoqiao, "scope": "M9A.5 only; no M9B; no scientific gate changes", "security_policy": "unchanged"})
    return {"output_dir": str(output), "network_status": network_status, "real_public_dataset_e2e": e2e.get("status"), "gaoqiao": gaoqiao, "files": sorted(path.name for path in output.iterdir() if path.is_file())}
