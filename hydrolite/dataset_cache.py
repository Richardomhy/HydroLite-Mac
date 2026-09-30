"""External content-addressed cache; failed downloads never become datasets."""
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import shutil
import tempfile
from urllib.parse import urlsplit

from hydrolite.app_settings import load_settings
from hydrolite.connectors.contracts import FetchedDataset
from hydrolite.connectors.transport import ConnectorError, open_public
from hydrolite.workspace import calculate_file_checksum

POLICIES = {"reuse_if_unchanged", "refresh_if_stale", "force_refresh", "offline_only"}
REPO = Path(__file__).resolve().parents[1]
SUFFIXES = {".csv", ".tsv", ".json", ".geojson", ".tif", ".tiff", ".nc", ".zip", ".xlsx"}
CONTENT_TYPES = {"text/csv", "text/plain", "text/tab-separated-values", "application/json", "application/geo+json", "image/tiff", "image/geotiff", "application/octet-stream", "application/zip", "application/x-netcdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def safe_destination(value):
    lexical = Path(value).expanduser().absolute()
    resolved = lexical.resolve()
    if any(part in {"data_raw", "tmp_emergency_0722"} for part in lexical.parts + resolved.parts):
        raise ConnectorError("unsafe_path", "Protected data directories cannot be written")
    for parent in (lexical, *lexical.parents):
        if parent.is_symlink() and not parent.exists():
            raise ConnectorError("data_cache_storage_unavailable", "Configured storage symlink is offline")
    if resolved.parts[:2] == ("/", "Volumes"):
        mount = Path(*resolved.parts[:3])
        if not mount.is_mount():
            raise ConnectorError("data_cache_storage_unavailable", "Configured external volume is not mounted; no fallback")
    return resolved


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        temp = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class DatasetCache:
    def __init__(self, root=None, max_bytes=50 * 1024 * 1024):
        settings = load_settings()
        default = Path(settings["runtime_directory"]) / "cache" / "datasets"
        self.root = safe_destination(root or os.getenv("HYDROLITE_DATA_CACHE_ROOT") or settings.get("data_cache_root") or default)
        if self.root == REPO or REPO in self.root.parents:
            raise ConnectorError("unsafe_cache_root", "Online cache must be outside the repository")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.max_bytes = int(max_bytes)

    def inspect_storage(self):
        try:
            root = safe_destination(self.root)
            existing = next((parent for parent in (root, *root.parents) if parent.exists()), None)
            if existing is None:
                raise ConnectorError("data_cache_storage_unavailable", "No mounted parent for configured cache")
            return {"status": "available", "cache_root": str(root), "external_volume": str(root).startswith("/Volumes/"), "free_bytes": shutil.disk_usage(existing).free}
        except (ConnectorError, OSError) as exc:
            return {"status": getattr(exc, "status", "data_cache_storage_unavailable"), "cache_root": str(self.root), "fallback": False}

    @staticmethod
    def key(candidate):
        return sha256(json.dumps(candidate.as_dict(), sort_keys=True, default=str).encode()).hexdigest()

    def lookup(self, candidate):
        safe_destination(self.root)
        index = self.root / "index" / (self.key(candidate) + ".json")
        try:
            value = json.loads(index.read_text())
            path = Path(value["local_path"]).resolve()
            if self.root not in path.parents or not path.is_file() or calculate_file_checksum(path) != value["checksum"]:
                return None
            return value
        except (OSError, KeyError, ValueError):
            return None

    def fetch(self, candidate, hosts, policy="reuse_if_unchanged", confirm_large=False, stale_seconds=86400, interval=0):
        if policy not in POLICIES:
            raise ValueError("Unknown cache policy")
        cached = self.lookup(candidate)
        if policy == "offline_only":
            return {**cached, "status": "offline_cached"} if cached else FetchedDataset("online_source_unavailable", candidate.as_dict(), error_message="No verified cached version").as_dict()
        if cached and policy == "refresh_if_stale":
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached["retrieved_at"])).total_seconds()
            except (ValueError, TypeError):
                age = stale_seconds + 1
            if age < stale_seconds:
                return {**cached, "status": "cached"}
        suffix = Path(urlsplit(candidate.source_url).path).suffix.lower()
        if suffix not in SUFFIXES:
            return FetchedDataset("unsupported_format", candidate.as_dict(), error_message="Only inert registered data formats are accepted").as_dict()
        limit = self.max_bytes * (4 if confirm_large else 1)
        if candidate.estimated_size is not None and candidate.estimated_size > limit:
            return FetchedDataset("approval_required", candidate.as_dict(), error_message="Dataset exceeds download size guard").as_dict()
        headers = {}
        if cached and policy != "force_refresh":
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            elif cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]
            elif policy == "reuse_if_unchanged":
                return {**cached, "status": "cached"}
        partial = None
        try:
            safe_destination(self.root)
            self.root.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(self.root).free < limit + 16 * 1024 * 1024:
                raise ConnectorError("data_cache_storage_unavailable", "Insufficient free cache space")
            with open_public(candidate.source_url, hosts, headers, interval) as response:
                if response.code == 304 and cached:
                    return {**cached, "status": "cached"}
                media = response.headers.get("Content-Type", "").split(";")[0].lower()
                if media not in CONTENT_TYPES or (candidate.content_type and media != candidate.content_type and media != "application/octet-stream"):
                    raise ConnectorError("invalid_content_type", "Unexpected provider content type")
                length = response.headers.get("Content-Length")
                if length and int(length) > limit:
                    raise ConnectorError("approval_required", "Content-Length exceeds size guard")
                with tempfile.NamedTemporaryFile(dir=self.root, suffix=".partial", delete=False) as handle:
                    partial = Path(handle.name)
                    size = 0
                    while chunk := response.read(65536):
                        size += len(chunk)
                        if size > limit:
                            raise ConnectorError("approval_required", "Streaming download exceeds size guard")
                        handle.write(chunk)
                if not size or (length and size != int(length)):
                    raise ConnectorError("invalid_dataset", "Empty or incomplete download")
                digest = calculate_file_checksum(partial)
                if candidate.checksum and digest.lower() != candidate.checksum.lower():
                    raise ConnectorError("checksum_mismatch", "Expected SHA-256 does not match")
                if suffix in {".zip", ".xlsx"}:
                    from hydrolite.data_upload import reject_unsafe_archive
                    result = reject_unsafe_archive(partial)
                    if result["status"] != "passed":
                        raise ConnectorError("unsafe_archive", "Archive failed existing Package Security checks")
                target = self.root / "objects" / digest / ("dataset" + suffix)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and calculate_file_checksum(target) == digest:
                    partial.unlink(missing_ok=True)
                else:
                    os.replace(partial, target)
                    target.chmod(0o444)
                if calculate_file_checksum(target) != digest:
                    raise ConnectorError("checksum_mismatch", "Cached object failed post-write verification")
                result = asdict(FetchedDataset("fetched", candidate.as_dict(), str(target), digest, datetime.now(timezone.utc).isoformat(), response.headers.get("ETag", ""), response.headers.get("Last-Modified", ""), processing_chain=("public_https", "content_type_size_check", "sha256")))
                atomic_json(self.root / "index" / (self.key(candidate) + ".json"), result)
                return result
        except (ConnectorError, OSError, ValueError) as exc:
            status = getattr(exc, "status", "online_source_unavailable")
            if cached and status in {"online_source_unavailable", "rate_limited", "authentication_required"}:
                return {**cached, "status": "offline_cached", "error_message": status}
            return FetchedDataset(status, candidate.as_dict(), error_message=str(exc) if isinstance(exc, ConnectorError) else "Download failed; inspect provider/storage availability").as_dict()
        finally:
            if partial:
                partial.unlink(missing_ok=True)
