from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import yaml

from hydrolite.gee_catalog.index import build_catalog_index, write_catalog_index
from hydrolite.gee_catalog.loader import fixture_records
from hydrolite.gee_catalog.normalizer import normalize_stac_collection
from hydrolite.gee_catalog.paths import CatalogPaths, get_catalog_paths
from hydrolite.gee_catalog.validation import validate_catalog
from hydrolite.__version__ import __version__


ROOT = Path(__file__).resolve().parents[2]
SOURCE_CONFIG = ROOT / "config" / "data_sources" / "gee_catalog_sources.yaml"


def _config() -> dict:
    return yaml.safe_load(SOURCE_CONFIG.read_text(encoding="utf-8"))


def _now() -> str: return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def _git_commit() -> str | None:
    try: return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception: return None


def _allowed(url: str) -> bool:
    return urlparse(url).hostname in set(_config()["allowed_hosts"])


def fetch_remote_json(url: str, timeout: int = 10, fetcher=urlopen) -> tuple[dict, dict]:
    if not _allowed(url): raise ValueError(f"Non-official catalog URL blocked: {url}")
    request = Request(url, headers={"User-Agent": "HydroLite-GEE-Catalog/1.0"})
    limits = _config()["limits"]
    last_error = None
    retry_count = int(limits.get("max_retries_per_url", 0))
    for attempt in range(retry_count + 1):
        try:
            with fetcher(request, timeout=timeout) as response:
                payload = response.read(limits["max_metadata_bytes"] + 1)
                if len(payload) > limits["max_metadata_bytes"]: raise ValueError("Metadata response exceeds configured size limit")
                headers = response.headers
                meta = {"source_url": url, "http_status": getattr(response, "status", 200), "etag": headers.get("ETag"), "last_modified": headers.get("Last-Modified"), "content_hash": hashlib.sha256(payload).hexdigest()}
            break
        except Exception as exc:
            last_error = exc
            if attempt == retry_count: raise
            time.sleep(0.25 * (2 ** attempt))
    return json.loads(payload.decode("utf-8")), meta


def _append_history(paths: CatalogPaths, entry: dict) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    with paths.history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": _now(), **entry}, ensure_ascii=False) + "\n")


def inspect_remote_catalog(fetcher=urlopen) -> dict:
    document, metadata = fetch_remote_json(_config()["public_https_uri"], fetcher=fetcher)
    return {**metadata, "source_type": document.get("type"), "link_count": len(document.get("links", [])), "status": "reachable"}


def fetch_catalog_child(link: dict, parent_url: str, fetcher=urlopen) -> tuple[dict, dict]:
    href = link.get("href")
    if not href: raise ValueError("STAC link has no href")
    return fetch_remote_json(urljoin(parent_url, href), fetcher=fetcher)


def traverse_stac_catalog(root: dict, config: dict | None = None, fetcher=urlopen, root_url: str | None = None) -> tuple[list[dict], list[dict]]:
    config = config or _config(); root_url = root_url or config["public_https_uri"]
    limits = config["limits"]
    max_records = int(limits["max_records"]); max_documents = int(limits.get("max_documents", 20000)); queue = [(root, root_url, 0)]; visited = set(); records: list[dict] = []; rejected: list[dict] = []
    while queue:
        document, source_url, depth = queue.pop(0)
        if source_url in visited: continue
        if len(visited) >= max_documents: raise ValueError(f"Catalog exceeds max_documents={max_documents}; candidate was not activated")
        visited.add(source_url)
        if document.get("id") and (document.get("type") in {"Collection", "Feature"} or document.get("asset_id")):
            try:
                record = normalize_stac_collection({**document, "stac_url": source_url})
                if record["asset_id"]: records.append(record)
            except Exception as exc: rejected.append({"source_url": source_url, "reason": str(exc)})
        if len(records) > max_records: raise ValueError(f"Catalog exceeds max_records={max_records}; candidate was not activated")
        for link in document.get("links", []) or []:
            if link.get("rel") not in {"child", "collection", "item"}: continue
            href = urljoin(source_url, str(link.get("href", "")))
            if not href or href in visited: continue
            if depth >= int(limits.get("max_depth", 20)):
                rejected.append({"source_url": href, "reason": "max_depth_reached"}); continue
            try: child, _ = fetch_catalog_child(link, source_url, fetcher); queue.append((child, href, depth + 1))
            except Exception as exc: rejected.append({"source_url": href, "reason": str(exc)})
    return records, rejected


def _write_candidate(paths: CatalogPaths, records: list[dict], rejected: list[dict], remote: dict) -> dict:
    paths.root.mkdir(parents=True, exist_ok=True)
    with gzip.open(paths.records, "wt", encoding="utf-8") as handle:
        for row in records: handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    write_catalog_index(build_catalog_index(records), paths.index)
    manifest = {"source_url": remote["source_url"], "source_type": "official_stac", "retrieval_time": _now(), "http_status": remote.get("http_status"), "etag": remote.get("etag"), "last_modified": remote.get("last_modified"), "content_hash": remote.get("content_hash"), "parser_version": "1", "hydrolite_version": __version__, "git_commit": _git_commit(), "record_count": len(records), "failure_count": len(rejected), "validation_status": "pending"}
    paths.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    paths.statistics.write_text(json.dumps({"record_count": len(records), "dataset_types": sorted({row.get("dataset_type") for row in records if row.get("dataset_type")})}, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def build_catalog_candidate(staging_dir: str | Path, records: list[dict], rejected_records: list[dict], remote: dict) -> dict:
    paths = get_catalog_paths(staging_dir); manifest = _write_candidate(paths, records, rejected_records, remote)
    validation = validate_catalog(records, manifest); paths.validation.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    (paths.root / "rejected_records.json").write_text(json.dumps(rejected_records, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["validation_status"] = validation["status"]; paths.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"paths": paths, "manifest": manifest, "validation": validation, "rejected_records": rejected_records}


def compare_catalog_candidate(current: list[dict], candidate: list[dict]) -> dict:
    current_ids, candidate_ids = {row["asset_id"] for row in current}, {row["asset_id"] for row in candidate}
    return {"added": sorted(candidate_ids - current_ids), "removed": sorted(current_ids - candidate_ids), "unchanged": len(current_ids & candidate_ids)}


def validate_catalog_candidate(candidate: dict) -> dict:
    validation = candidate["validation"]
    valid = validation["status"] in {"valid", "valid_with_warnings"} and candidate["manifest"]["record_count"] > len(fixture_records())
    return {"status": "valid" if valid else "invalid", "validation": validation, "reason": None if valid else "Candidate must exceed fixture size and pass validation."}


def activate_catalog_candidate(candidate: dict, catalog_root: str | Path | None = None) -> dict:
    live = get_catalog_paths(catalog_root); stage = candidate["paths"]
    check = validate_catalog_candidate(candidate)
    if check["status"] != "valid": return {"status": "refresh_failed_previous_catalog_preserved", **check}
    live.root.parent.mkdir(parents=True, exist_ok=True); live.backups.mkdir(parents=True, exist_ok=True)
    backup = live.backups / f"catalog-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    if live.records.exists(): shutil.copytree(live.root, backup, dirs_exist_ok=True, ignore=shutil.ignore_patterns("backups", "staging"))
    for source, target in ((stage.records, live.records), (stage.index, live.index), (stage.manifest, live.manifest), (stage.validation, live.validation), (stage.statistics, live.statistics)):
        shutil.copy2(source, target)
    _append_history(live, {"status": "activated", "record_count": candidate["manifest"]["record_count"]})
    return {"status": "refreshed", "catalog_root": str(live.root), "backup": str(backup) if backup.exists() else None, "record_count": candidate["manifest"]["record_count"]}


def rollback_catalog_refresh(catalog_root: str | Path | None = None) -> dict:
    live = get_catalog_paths(catalog_root); backups = sorted(live.backups.glob("catalog-*"))
    if not backups: return {"status": "no_backup"}
    backup = backups[-1]
    for name in ("catalog.jsonl.gz", "catalog_index.parquet", "manifest.json", "validation.json", "catalog_statistics.json"):
        source = backup / name
        if source.exists(): shutil.copy2(source, live.root / name)
    return {"status": "rolled_back", "backup": str(backup)}


def refresh_catalog(mode: str = "dry-run", *, execute: bool | None = None, catalog_root: str | Path | None = None, fetcher=urlopen) -> dict:
    execute = mode == "execute" if execute is None else execute
    live = get_catalog_paths(catalog_root)
    try: remote = inspect_remote_catalog(fetcher)
    except Exception as exc:
        result = {"status": "refresh_failed_previous_catalog_preserved", "execute": execute, "error": str(exc), "catalog": live.root.as_posix()}
        if execute and live.root.exists(): _append_history(live, result)
        return result
    if not execute:
        return {"status": "dry_run", "execute": False, "remote": remote, "would_write": str(live.root), "limits": _config()["limits"]}
    try:
        root, _ = fetch_remote_json(_config()["public_https_uri"], fetcher=fetcher)
        records, rejected = traverse_stac_catalog(root, fetcher=fetcher)
        stage = live.staging / f"refresh-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
        candidate = build_catalog_candidate(stage, records, rejected, remote)
        result = activate_catalog_candidate(candidate, live.root)
        return {**result, "rejected_records": len(rejected), "change": compare_catalog_candidate(fixture_records(), records)}
    except Exception as exc:
        result = {"status": "refresh_failed_previous_catalog_preserved", "execute": True, "error": str(exc), "catalog": str(live.root)}
        if live.root.exists(): _append_history(live, result)
        return result
