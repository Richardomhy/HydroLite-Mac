from __future__ import annotations

import gzip
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess

import yaml

from hydrolite.__version__ import __version__
from hydrolite.gee_catalog.index import build_catalog_index, write_catalog_index
from hydrolite.gee_catalog.loader import fixture_records
from hydrolite.gee_catalog.normalizer import normalize_stac_collection
from hydrolite.gee_catalog.paths import CatalogPaths, get_catalog_paths
from hydrolite.gee_catalog.transport import fetch_catalog_object, resolve_stac_link
from hydrolite.gee_catalog.validation import validate_catalog


ROOT = Path(__file__).resolve().parents[2]
SOURCE_CONFIG = ROOT / "config" / "data_sources" / "gee_catalog_sources.yaml"


def _config() -> dict:
    return yaml.safe_load(SOURCE_CONFIG.read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def _append_history(paths: CatalogPaths, entry: dict) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    with paths.history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": _now(), **entry}, ensure_ascii=False) + "\n")


def inspect_remote_catalog() -> dict:
    config = _config()
    root, result, attempts = fetch_catalog_object(config["canonical_uri"], transport_priority=config["transport_priority"])
    payload = result.as_dict()
    payload["attempts"] = [item.as_dict() for item in attempts]
    if root is None:
        return {"status": "transport_unavailable", "root": None, "transport": payload}
    return {
        "status": "official_root_only", "root": root,
        "transport": payload, "root_catalog_verified": True,
        "source_type": root.get("type"), "link_count": len(root.get("links", [])),
    }


def traverse_stac_catalog(root: dict, config: dict | None = None, *, root_uri: str | None = None, session: dict | None = None, object_fetcher=fetch_catalog_object) -> tuple[list[dict], list[dict]]:
    """Traverse STAC using one selected safe transport, preserving child failures."""
    config = config or _config()
    limits = config["limits"]
    root_uri = root_uri or config["canonical_uri"]
    session = session if session is not None else {}
    session.update({"root_catalog_verified": True, "objects": 1, "accepted": 0, "truncated": False, "transport_id": None})
    queue = [(root, root_uri, 0)]
    visited: set[str] = set()
    records: list[dict] = []
    rejected: list[dict] = []
    max_records = int(limits["max_records"])
    max_documents = int(limits.get("max_documents", 20000))
    priority = config.get("transport_priority", [])
    while queue:
        pending: dict[str, int] = {}
        for document, uri, depth in queue:
            if uri in visited:
                continue
            if len(visited) >= max_documents:
                session["truncated"] = True; rejected.append({"source_url": uri, "reason": "max_documents_reached"}); break
            visited.add(uri)
            if document.get("id") and document.get("type") in {"Collection", "Feature"}:
                try:
                    record = normalize_stac_collection({**document, "stac_url": uri})
                    if record["asset_id"]:
                        records.append(record); session["accepted"] += 1
                except Exception as exc:
                    rejected.append({"source_url": uri, "reason": "normalization_failed", "message": str(exc)[:300]})
            for link in document.get("links", []) or []:
                if link.get("rel") not in {"child", "collection", "item"}:
                    continue
                try:
                    child_uri = resolve_stac_link(uri, str(link.get("href", "")))
                except Exception as exc:
                    rejected.append({"source_url": str(link.get("href", "")), "reason": "unsafe_link", "message": str(exc)[:300]}); continue
                if child_uri not in visited:
                    pending.setdefault(child_uri, depth + 1)
        if len(records) > max_records:
            session["truncated"] = True; rejected.append({"reason": "max_records_reached"}); break
        queue = []
        with ThreadPoolExecutor(max_workers=max(1, min(int(limits.get("max_concurrency", 4)), 4))) as executor:
            futures = {executor.submit(object_fetcher, uri, transport_priority=priority): (uri, depth) for uri, depth in pending.items() if depth <= int(limits.get("max_depth", 20))}
            for future in as_completed(futures):
                child_uri, depth = futures[future]; session["objects"] += 1
                try:
                    child, transport, _attempts = future.result()
                except Exception as exc:
                    rejected.append({"source_url": child_uri, "reason": "transport_failed", "message": str(exc)[:300]}); continue
                session["transport_id"] = session["transport_id"] or transport.transport_id
                if child is None:
                    rejected.append({"source_url": child_uri, "reason": transport.error_type or "transport_failed", "message": transport.error_message}); continue
                if not isinstance(child, dict) or not child.get("type"):
                    rejected.append({"source_url": child_uri, "reason": "invalid_stac"}); continue
                queue.append((child, child_uri, depth))
        for child_uri, depth in pending.items():
            if depth > int(limits.get("max_depth", 20)):
                rejected.append({"source_url": child_uri, "reason": "max_depth_reached"})
    session["visited"] = len(visited)
    return records, rejected


def _completeness(session: dict, rejected: list[dict], config: dict) -> str:
    if session.get("truncated"):
        return "official_partial"
    denominator = max(1, int(session.get("objects", 0)))
    ratio = len(rejected) / denominator
    if ratio > float(config["limits"].get("max_failure_rate", 0.05)):
        return "official_partial"
    return "official_complete_with_warnings" if rejected else "official_complete"


def _write_candidate(paths: CatalogPaths, records: list[dict], rejected: list[dict], remote: dict, completeness: str, session: dict) -> dict:
    paths.root.mkdir(parents=True, exist_ok=True)
    with gzip.open(paths.records, "wt", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    write_catalog_index(build_catalog_index(records), paths.index)
    manifest = {
        "source_url": remote["transport"]["canonical_uri"], "resolved_uri": remote["transport"]["resolved_uri"],
        "source_type": "official_stac", "retrieval_time": _now(), "http_status": None,
        "content_hash": remote["transport"].get("checksum"), "parser_version": "1.1",
        "hydrolite_version": __version__, "git_commit": _git_commit(), "record_count": len(records),
        "failure_count": len(rejected), "root_catalog_verified": True, "catalog_completeness": completeness,
        "transport_id": session.get("transport_id") or remote["transport"]["transport_id"],
        "traversal_objects": session.get("objects", 0), "validation_status": "pending",
    }
    paths.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    paths.statistics.write_text(json.dumps({"record_count": len(records), "dataset_types": sorted({row.get("dataset_type") for row in records if row.get("dataset_type")}), "accepted": session.get("accepted", 0), "rejected": len(rejected)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def build_catalog_candidate(staging_dir: str | Path, records: list[dict], rejected_records: list[dict], remote: dict, *, completeness: str = "official_complete", session: dict | None = None) -> dict:
    paths = get_catalog_paths(staging_dir)
    remote = remote if "transport" in remote else {"transport": {"canonical_uri": remote["source_url"], "resolved_uri": remote["source_url"], "checksum": remote.get("content_hash"), "transport_id": "test"}}
    manifest = _write_candidate(paths, records, rejected_records, remote, completeness, session or {})
    validation = validate_catalog(records, manifest)
    paths.validation.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    (paths.root / "rejected_records.json").write_text(json.dumps(rejected_records, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["validation_status"] = validation["status"]
    paths.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"paths": paths, "manifest": manifest, "validation": validation, "rejected_records": rejected_records}


def compare_catalog_candidate(current: list[dict], candidate: list[dict]) -> dict:
    current_ids, candidate_ids = {row["asset_id"] for row in current}, {row["asset_id"] for row in candidate}
    return {"added": sorted(candidate_ids - current_ids), "removed": sorted(current_ids - candidate_ids), "unchanged": len(current_ids & candidate_ids)}


def validate_catalog_candidate(candidate: dict) -> dict:
    validation = candidate["validation"]
    complete = candidate["manifest"].get("catalog_completeness") in {"official_complete", "official_complete_with_warnings"}
    valid = complete and validation["status"] in {"valid", "valid_with_warnings"} and candidate["manifest"]["record_count"] > len(fixture_records())
    return {"status": "valid" if valid else "invalid", "validation": validation, "reason": None if valid else "Candidate must be complete, exceed fixture size, and pass validation."}


def activate_catalog_candidate(candidate: dict, catalog_root: str | Path | None = None) -> dict:
    live = get_catalog_paths(catalog_root); stage = candidate["paths"]
    check = validate_catalog_candidate(candidate)
    if check["status"] != "valid":
        return {"status": "refresh_failed_previous_catalog_preserved", **check}
    live.root.parent.mkdir(parents=True, exist_ok=True); live.backups.mkdir(parents=True, exist_ok=True)
    backup = live.backups / f"catalog-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    if live.records.exists():
        shutil.copytree(live.root, backup, dirs_exist_ok=True, ignore=shutil.ignore_patterns("backups", "staging"))
    for source, target in ((stage.records, live.records), (stage.index, live.index), (stage.manifest, live.manifest), (stage.validation, live.validation), (stage.statistics, live.statistics)):
        shutil.copy2(source, target)
    _append_history(live, {"status": "activated", "record_count": candidate["manifest"]["record_count"], "catalog_completeness": candidate["manifest"]["catalog_completeness"]})
    return {"status": "refreshed", "catalog_root": str(live.root), "backup": str(backup) if backup.exists() else None, "record_count": candidate["manifest"]["record_count"], "catalog_completeness": candidate["manifest"]["catalog_completeness"]}


def rollback_catalog_refresh(catalog_root: str | Path | None = None) -> dict:
    live = get_catalog_paths(catalog_root); backups = sorted(live.backups.glob("catalog-*"))
    if not backups:
        return {"status": "no_backup"}
    backup = backups[-1]
    for name in ("catalog.jsonl.gz", "catalog_index.parquet", "manifest.json", "validation.json", "catalog_statistics.json"):
        source = backup / name
        if source.exists():
            shutil.copy2(source, live.root / name)
    return {"status": "rolled_back", "backup": str(backup)}


def refresh_catalog(mode: str = "dry-run", *, execute: bool | None = None, catalog_root: str | Path | None = None) -> dict:
    execute = mode == "execute" if execute is None else execute
    live = get_catalog_paths(catalog_root)
    remote = inspect_remote_catalog()
    if remote["root"] is None:
        return {"status": "refresh_failed_previous_catalog_preserved", "execute": execute, "transport": remote["transport"], "catalog": str(live.root), "fixture_fallback": True}
    if not execute:
        return {"status": "official_root_only", "execute": False, "root_catalog_verified": True, "remote": remote["transport"], "root_type": remote["source_type"], "link_count": remote["link_count"], "would_write": str(live.root)}
    session: dict = {}
    records, rejected = traverse_stac_catalog(remote["root"], _config(), root_uri=remote["transport"]["canonical_uri"], session=session)
    completeness = _completeness(session, rejected, _config())
    if completeness == "official_partial":
        return {"status": "official_partial", "execute": True, "root_catalog_verified": True, "record_count": len(records), "accepted": session.get("accepted", 0), "rejected": len(rejected), "traversal_objects": session.get("objects", 0), "fixture_fallback": not live.records.exists()}
    stage = live.staging / f"refresh-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    candidate = build_catalog_candidate(stage, records, rejected, remote, completeness=completeness, session=session)
    result = activate_catalog_candidate(candidate, live.root)
    return {**result, "accepted": session.get("accepted", 0), "rejected": len(rejected), "traversal_objects": session.get("objects", 0), "change": compare_catalog_candidate(fixture_records(), records)}
