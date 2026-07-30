from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import json
import xml.etree.ElementTree as ET

from hydrolite.release_metadata import compare_release_versions, load_version


def validate_update_url(url: str) -> bool:
    if urlparse(url).scheme != "https":
        raise ValueError("Update URLs must use HTTPS")
    return True


def load_update_configuration(path: str | Path | None = None) -> dict:
    if not path:
        return {"sparkle_integrated": False, "feed_url": "", "public_key": "", "status": "configured_no_feed"}
    source = Path(path)
    return json.loads(source.read_text(encoding="utf-8")) if source.exists() else {"sparkle_integrated": False, "feed_url": "", "public_key": "", "status": "configured_no_feed"}


def inspect_update_status(path: str | Path | None = None) -> dict:
    config = load_update_configuration(path)
    feed = str(config.get("feed_url") or "")
    if feed:
        validate_update_url(feed)
    readiness = (
        "feed_available" if feed and config.get("public_key")
        else "framework_integrated_signing_key_missing" if feed and config.get("sparkle_integrated")
        else "framework_ready_configuration_missing"
    )
    return {
        "status": "passed",
        "sparkle_integrated": bool(config.get("sparkle_integrated")),
        "feed_configured": bool(feed),
        "update_readiness": readiness,
        "manual_manifest_fallback": True,
    }


def parse_appcast(path: str | Path) -> list[dict]:
    root = ET.parse(path).getroot()
    rows = []
    for enclosure in root.findall(".//enclosure"):
        url = enclosure.attrib.get("url", "")
        if url:
            validate_update_url(url)
        rows.append({"url": url, "version": enclosure.attrib.get("sparkle:version", enclosure.attrib.get("{http://www.andymatuschak.org/xml-namespaces/sparkle}version", ""))})
    return rows


def check_manual_release_manifest(path: str | Path) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    remote = str(manifest.get("version") or "")
    comparison = compare_release_versions(load_version()["version"], remote)
    signed = bool(manifest.get("code_signing", {}).get("developer_id"))
    return {"status": "update_available" if comparison < 0 else "current", "remote_version": remote, "signed_update_required": True, "install_allowed": comparison < 0 and signed}
