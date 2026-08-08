"""Safe transport helpers for the public Earth Engine STAC bucket.

This module reads metadata only.  It never initializes Earth Engine or uses a
user-supplied local path as a catalog URI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import PurePosixPath
import shutil
import subprocess
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


OFFICIAL_BUCKET = "earthengine-stac"
OFFICIAL_HTTPS_HOSTS = {"storage.googleapis.com", f"{OFFICIAL_BUCKET}.storage.googleapis.com"}
_ANONYMOUS_CLIENT = None
_AUTHENTICATED_CLIENT = None


@dataclass(frozen=True)
class GeeCatalogTransportResult:
    transport_id: str
    status: str
    canonical_uri: str
    resolved_uri: str | None = None
    authentication_mode: str = "none"
    bytes_received: int = 0
    content_type: str | None = None
    checksum: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    provenance: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _result(transport_id: str, uri: str, *, status: str, started: float, payload: bytes | None = None, content_type: str | None = None, authentication_mode: str = "none", error: Exception | None = None, resolved_uri: str | None = None, provenance: dict[str, Any] | None = None) -> GeeCatalogTransportResult:
    return GeeCatalogTransportResult(
        transport_id=transport_id, status=status, canonical_uri=uri, resolved_uri=resolved_uri or uri,
        authentication_mode=authentication_mode, bytes_received=len(payload or b""), content_type=content_type,
        checksum=hashlib.sha256(payload).hexdigest() if payload is not None else None,
        error_type=classify_transport_error(error) if error else None,
        error_message=_sanitize_error(error) if error else None,
        latency_ms=round((time.monotonic() - started) * 1000), provenance=provenance or {},
    )


def _sanitize_error(error: Exception | None) -> str | None:
    if error is None:
        return None
    text = str(error).replace("Bearer ", "Bearer [redacted]")
    for marker in ("access_token=", "refresh_token=", "client_secret="):
        if marker in text:
            text = text.split(marker, 1)[0] + marker + "[redacted]"
    return text[:500]


def classify_transport_error(error: Exception | None) -> str | None:
    if error is None:
        return None
    status = getattr(error, "code", None) or getattr(getattr(error, "response", None), "status_code", None)
    message = str(error).lower()
    if status == 404 or "no such object" in message or "not found" in message:
        return "official_object_not_found"
    if status in {401, 403}:
        return "anonymous_access_denied"
    if "default credentials" in message or "could not automatically determine credentials" in message:
        return "authentication_required"
    if "timed out" in message or "timeout" in message:
        return "network_timeout"
    if "name or service not known" in message or "nodename nor servname" in message or "temporary failure in name resolution" in message:
        return "dns_failure"
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "transport_dependency_missing"
    if isinstance(error, json.JSONDecodeError):
        return "invalid_stac"
    return "transport_unavailable"


def parse_gs_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError("A catalog object must use gs://bucket/object syntax")
    if parsed.netloc != OFFICIAL_BUCKET:
        raise ValueError("Only the official earthengine-stac bucket is allowed")
    path = parsed.path.lstrip("/")
    if ".." in PurePosixPath(path).parts:
        raise ValueError("Parent-path traversal is not allowed in catalog URIs")
    return parsed.netloc, path


def _https_to_gs(uri: str) -> str | None:
    parsed = urlparse(uri)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HTTPS_HOSTS:
        return None
    path = parsed.path.lstrip("/")
    if parsed.hostname == "storage.googleapis.com":
        if not path.startswith(f"{OFFICIAL_BUCKET}/"):
            return None
        path = path.removeprefix(f"{OFFICIAL_BUCKET}/")
    return f"gs://{OFFICIAL_BUCKET}/{path}" if path else None


def resolve_stac_link(parent_uri: str, href: str) -> str:
    """Resolve only official STAC child links without allowing path escape."""
    href = str(href or "").strip()
    if not href:
        raise ValueError("STAC link has no href")
    parsed = urlparse(href)
    if parsed.scheme == "gs":
        parse_gs_uri(href)
        return href
    if parsed.scheme == "https":
        gs_uri = _https_to_gs(href)
        if not gs_uri:
            raise ValueError("Only official Google Storage HTTPS STAC links are allowed")
        return gs_uri
    if parsed.scheme or href.startswith("//"):
        raise ValueError("Only gs://, official HTTPS, and relative STAC links are allowed")
    bucket, parent_path = parse_gs_uri(parent_uri)
    candidate = PurePosixPath(parent_path).parent.joinpath(href)
    if ".." in candidate.parts or not str(candidate).startswith("catalog/"):
        raise ValueError("Relative STAC link escapes the official catalog prefix")
    return f"gs://{bucket}/{candidate.as_posix()}"


def detect_available_transports() -> list[dict[str, Any]]:
    try:
        import google.cloud.storage  # noqa: F401
        gcs_available = True
    except Exception:
        gcs_available = False
    return [
        {"transport_id": "google_cloud_storage_anonymous", "available": gcs_available, "authentication_mode": "anonymous"},
        {"transport_id": "google_cloud_storage_authenticated", "available": gcs_available, "authentication_mode": "application_default_credentials"},
        {"transport_id": "gcloud_storage", "available": bool(shutil.which("gcloud")), "authentication_mode": "gcloud"},
        {"transport_id": "gsutil", "available": bool(shutil.which("gsutil")), "authentication_mode": "gsutil"},
        {"transport_id": "verified_https", "available": True, "authentication_mode": "none", "candidate_only": True},
        {"transport_id": "fixture", "available": True, "authentication_mode": "none"},
    ]


def read_with_google_cloud_storage(uri: str, *, anonymous: bool = True, timeout: int = 30) -> tuple[bytes | None, GeeCatalogTransportResult]:
    global _ANONYMOUS_CLIENT, _AUTHENTICATED_CLIENT
    started = time.monotonic(); transport_id = "google_cloud_storage_anonymous" if anonymous else "google_cloud_storage_authenticated"
    try:
        from google.cloud import storage
        bucket_name, object_name = parse_gs_uri(uri)
        if anonymous:
            _ANONYMOUS_CLIENT = _ANONYMOUS_CLIENT or storage.Client.create_anonymous_client()
            client = _ANONYMOUS_CLIENT
        else:
            _AUTHENTICATED_CLIENT = _AUTHENTICATED_CLIENT or storage.Client()
            client = _AUTHENTICATED_CLIENT
        blob = client.bucket(bucket_name).blob(object_name)
        payload = blob.download_as_bytes(timeout=timeout)
        return payload, _result(transport_id, uri, status="success", started=started, payload=payload, content_type=blob.content_type, authentication_mode="anonymous" if anonymous else "application_default_credentials", provenance={"bucket": bucket_name, "object": object_name})
    except Exception as exc:
        return None, _result(transport_id, uri, status="failed", started=started, authentication_mode="anonymous" if anonymous else "application_default_credentials", error=exc)


def _read_subprocess(command: list[str], transport_id: str, uri: str, authentication_mode: str) -> tuple[bytes | None, GeeCatalogTransportResult]:
    started = time.monotonic()
    if not shutil.which(command[0]):
        return None, _result(transport_id, uri, status="unavailable", started=started, authentication_mode=authentication_mode, error=ModuleNotFoundError(command[0]))
    try:
        completed = subprocess.run(command, capture_output=True, timeout=30, check=False)
        if completed.returncode:
            return None, _result(transport_id, uri, status="failed", started=started, authentication_mode=authentication_mode, error=RuntimeError(completed.stderr.decode("utf-8", "replace")))
        return completed.stdout, _result(transport_id, uri, status="success", started=started, payload=completed.stdout, authentication_mode=authentication_mode)
    except Exception as exc:
        return None, _result(transport_id, uri, status="failed", started=started, authentication_mode=authentication_mode, error=exc)


def read_with_gcloud(uri: str) -> tuple[bytes | None, GeeCatalogTransportResult]:
    return _read_subprocess(["gcloud", "storage", "cat", uri], "gcloud_storage", uri, "gcloud")


def read_with_gsutil(uri: str) -> tuple[bytes | None, GeeCatalogTransportResult]:
    return _read_subprocess(["gsutil", "cat", uri], "gsutil", uri, "gsutil")


def read_with_https(uri: str, *, timeout: int = 30, opener=urlopen) -> tuple[bytes | None, GeeCatalogTransportResult]:
    started = time.monotonic()
    try:
        gs_uri = _https_to_gs(uri)
        if not gs_uri:
            raise ValueError("HTTPS transport only permits official Google Storage URLs")
        with opener(Request(uri, headers={"User-Agent": "HydroLite-GEE-Catalog/1.1"}), timeout=timeout) as response:
            payload = response.read()
            return payload, _result("verified_https", gs_uri, status="success", started=started, payload=payload, content_type=response.headers.get("Content-Type"), resolved_uri=uri)
    except Exception as exc:
        return None, _result("verified_https", uri, status="failed", started=started, error=exc)


def read_gs_uri(uri: str, transport_id: str = "google_cloud_storage_anonymous") -> tuple[bytes | None, GeeCatalogTransportResult]:
    if transport_id == "google_cloud_storage_anonymous": return read_with_google_cloud_storage(uri, anonymous=True)
    if transport_id == "google_cloud_storage_authenticated": return read_with_google_cloud_storage(uri, anonymous=False)
    if transport_id == "gcloud_storage": return read_with_gcloud(uri)
    if transport_id == "gsutil": return read_with_gsutil(uri)
    raise ValueError(f"Unsupported GCS transport: {transport_id}")


def select_catalog_transport(config: dict[str, Any]) -> str:
    available = {item["transport_id"]: item["available"] for item in detect_available_transports()}
    return next((item for item in config.get("transport_priority", []) if available.get(item)), "fixture")


def fetch_catalog_object(uri: str, *, transport_priority: list[str] | None = None) -> tuple[dict[str, Any] | None, GeeCatalogTransportResult, list[GeeCatalogTransportResult]]:
    priority = transport_priority or ["google_cloud_storage_anonymous", "google_cloud_storage_authenticated", "gcloud_storage", "gsutil", "verified_https"]
    canonical_uri = _https_to_gs(uri) or uri
    parse_gs_uri(canonical_uri)
    attempts: list[GeeCatalogTransportResult] = []
    for transport_id in priority:
        if transport_id == "verified_https":
            https_uri = f"https://storage.googleapis.com/{OFFICIAL_BUCKET}/{parse_gs_uri(canonical_uri)[1]}"
            payload, result = read_with_https(https_uri)
        else:
            payload, result = read_gs_uri(canonical_uri, transport_id)
        attempts.append(result)
        if payload is None:
            continue
        try:
            return json.loads(payload.decode("utf-8")), result, attempts
        except Exception as exc:
            attempts[-1] = _result(result.transport_id, canonical_uri, status="failed", started=time.monotonic(), error=exc, authentication_mode=result.authentication_mode)
    return None, attempts[-1] if attempts else _result("fixture", canonical_uri, status="unavailable", started=time.monotonic(), error=RuntimeError("No transport attempts")), attempts


def write_transport_diagnosis(output_dir: str = "output/gee_catalog_intelligence") -> dict[str, str]:
    from pathlib import Path
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    payload = {"canonical_uri": f"gs://{OFFICIAL_BUCKET}/catalog/catalog.json", "available_transports": detect_available_transports()}
    json_path = output / "transport_diagnosis.json"; md_path = output / "transport_diagnosis.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text("# GEE STAC transport diagnosis\n\n" + "\n".join(f"- {item['transport_id']}: {'available' if item['available'] else 'unavailable'}" for item in payload["available_transports"]) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
