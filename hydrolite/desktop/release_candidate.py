"""macOS release-candidate audits; never creates or guesses production credentials."""

from __future__ import annotations

from base64 import b64decode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import plistlib
import re
import subprocess
import zipfile

import pandas as pd

from hydrolite.desktop.security_audit import audit_desktop_bundle
from hydrolite.desktop.signing_audit import audit_macos_signature, detect_developer_identities, inventory_macho_files


ROOT = Path(__file__).resolve().parents[2]
RC_NAME = "HydroLite-Studio-0.7.0-RC1-arm64"
EXPECTED_BUNDLE_ID = "com.hydrolite.studio"


def _run(command: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, errors="replace", check=False, timeout=timeout)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_app_bundle(app: str | Path) -> str:
    root = Path(app)
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(bytes.fromhex(hash_file(path)))
    return digest.hexdigest()


def calculate_next_build_number(root: str | Path = ROOT) -> int:
    base = Path(root)
    known = []
    paths = [base / "desktop/macos/HydroLiteStudio/Resources/Info.plist", *base.glob("dist/macos/*.app/Contents/Info.plist")]
    for path in paths:
        try:
            known.append(int(plistlib.loads(path.read_bytes()).get("CFBundleVersion", 0)))
        except (OSError, ValueError, TypeError, plistlib.InvalidFileException):
            pass
    count = _run(["git", "rev-list", "--count", "HEAD"]).stdout.strip()
    known.append(int(count or 0))
    return max(known, default=0) + 1


def build_environment() -> dict[str, Any]:
    developer_dir = os.getenv("DEVELOPER_DIR") or ("/Applications/Xcode.app/Contents/Developer" if Path("/Applications/Xcode.app/Contents/Developer").is_dir() else "unavailable")
    env = {**os.environ, "DEVELOPER_DIR": developer_dir} if developer_dir != "unavailable" else os.environ
    xcode = subprocess.run(["xcodebuild", "-version"], env=env, capture_output=True, text=True, check=False).stdout.splitlines()
    swift = _run(["swift", "--version"]).stdout.splitlines()
    versions = {}
    for name in ("pyinstaller", "streamlit", "python"):
        if name == "python":
            versions[name] = platform.python_version()
        else:
            try: versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError: versions[name] = "unavailable"
    return {
        "macos": platform.mac_ver()[0], "architecture": platform.machine(),
        "xcode": " / ".join(xcode) or "unavailable", "developer_dir": developer_dir,
        "swift": swift[0] if swift else "unavailable", **versions, "sparkle": "2.9.4",
    }


def audit_info_plist(app: str | Path) -> dict[str, Any]:
    info = plistlib.loads((Path(app) / "Contents/Info.plist").read_bytes())
    feed = str(info.get("SUFeedURL") or "")
    errors = []
    if info.get("CFBundleIdentifier") != EXPECTED_BUNDLE_ID: errors.append("unexpected_bundle_id")
    if not feed.startswith("https://"): errors.append("feed_must_use_https")
    if any(marker in json.dumps(info) for marker in ("localhost", "127.0.0.1", "/Users/")): errors.append("unexpected_debug_or_absolute_value")
    return {
        "status": "passed" if not errors else "failed", "errors": errors,
        "bundle_id": info.get("CFBundleIdentifier"), "marketing_version": info.get("CFBundleShortVersionString"),
        "build_number": info.get("CFBundleVersion"), "minimum_macos": info.get("LSMinimumSystemVersion"),
        "feed_url": feed, "sparkle_public_key": "configured" if info.get("SUPublicEDKey") else "missing",
        "automatic_checks": bool(info.get("SUEnableAutomaticChecks", False)),
    }


def audit_entitlements(app: str | Path) -> dict[str, Any]:
    result = _run(["codesign", "-d", "--entitlements", ":-", str(app)])
    text = result.stdout + result.stderr
    keys = {
        "get_task_allow": "com.apple.security.get-task-allow",
        "disable_library_validation": "com.apple.security.cs.disable-library-validation",
        "allow_jit": "com.apple.security.cs.allow-jit",
        "allow_unsigned_executable_memory": "com.apple.security.cs.allow-unsigned-executable-memory",
        "network_client": "com.apple.security.network.client",
        "network_server": "com.apple.security.network.server",
    }
    values = {name: key in text and re.search(rf"{re.escape(key)}.*?<true", text, re.S) is not None for name, key in keys.items()}
    return {"status": "failed" if values["get_task_allow"] else "passed", **values, "least_privilege": not any(values.values())}


def architecture_inventory(app: str | Path) -> dict[str, Any]:
    def normalized_architecture(value: str) -> str:
        if "arm64" in value and "x86_64" in value:
            return "universal2"
        if "arm64" in value:
            return "arm64"
        if "x86_64" in value:
            return "x86_64"
        return "unknown"

    raw_rows = inventory_macho_files(app)
    rows = []
    for row in raw_rows:
        signature = row.get("signature", "")
        rows.append({
            "relative_path": row["path"], "type": "Mach-O", "architecture": normalized_architecture(row["architecture"]),
            "signed": row["signed"],
            "signing_identity": "ad_hoc" if "Signature=adhoc" in signature else "developer_id" if "Authority=Developer ID Application" in signature else "unknown",
            "hardened_runtime": "flags=0x10000(runtime)" in signature,
            "timestamp_state": "present" if "Timestamp=" in signature else "absent",
        })
    architectures = sorted({row["architecture"] for row in rows})
    arm64_compatible = bool(rows) and all(item in {"arm64", "universal2"} for item in architectures)
    return {
        "status": "passed" if arm64_compatible else "failed",
        "supported_architecture": "arm64" if arm64_compatible else architectures,
        "architectures_present": architectures,
        "macho_count": len(rows), "nested_code_count": max(0, len(rows) - 1), "items": rows,
    }


def validate_update_signature_metadata(signature: str, public_key_available: bool) -> dict[str, Any]:
    try: valid_format = len(b64decode(signature, validate=True)) == 64
    except Exception: valid_format = False
    valid = bool(public_key_available and valid_format)
    return {"status": "passed" if valid else "blocked", "reason": "valid_metadata" if valid else "invalid_or_unverifiable_signature"}


def audit_zip(path: str | Path) -> dict[str, Any]:
    forbidden = ("data_raw/", "external/", ".env", ".sqlite", ".dss", ".hdf5", ".pt", ".pth", ".ckpt", ".p8", ".p12")
    findings = []
    warnings = []
    text_suffixes = {".csv", ".html", ".json", ".md", ".plist", ".py", ".toml", ".txt", ".xml", ".yaml", ".yml"}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            lower = name.lower()
            if any(marker in lower for marker in forbidden): findings.append({"file": name, "rule": "forbidden_member"})
            if name.endswith("/"): continue
            data = archive.read(name)
            if b"BEGIN PRIVATE KEY" in data:
                findings.append({"file": name, "rule": "sensitive_or_absolute_text"})
            if b"/Users/" in data:
                target = findings if Path(name).suffix.lower() in text_suffixes else warnings
                target.append({"file": name, "rule": "absolute_text" if target is findings else "binary_build_metadata"})
    return {"status": "passed" if not findings else "failed", "findings": findings, "warnings": warnings}


def assess_release_readiness(signing: dict, info: dict, security: dict, architecture: dict, zip_audit: dict | None = None, entitlements: dict | None = None) -> dict[str, Any]:
    identities = detect_developer_identities()
    developer_id = signing.get("signing_mode") == "developer_id" and signing.get("status") == "passed"
    notary_profile = bool(os.getenv("HYDROLITE_NOTARY_PROFILE"))
    sparkle_public = info.get("sparkle_public_key") == "configured"
    blockers = []
    if not identities: blockers.append("developer_id_missing")
    if not notary_profile: blockers.append("notary_credentials_missing")
    if not sparkle_public: blockers.append("sparkle_signing_key_missing")
    required = [info["status"], security["status"], architecture["status"], signing.get("status")]
    if zip_audit: required.append(zip_audit["status"])
    if entitlements: required.append(entitlements["status"])
    build_ok = all(status == "passed" for status in required)
    return {
        "build_readiness": "internal_rc_ready" if build_ok else "blocked",
        "signing_readiness": "signed_rc_ready" if developer_id else "ad_hoc_internal_rc" if signing.get("status") == "passed" else "blocked",
        "notarization_readiness": "ready" if developer_id and notary_profile else "credentials_required",
        "gatekeeper_readiness": "requires_notarization" if not developer_id else "pending_notarization",
        "secure_auto_update_readiness": "ready" if developer_id and notary_profile and sparkle_public else "blocked_signing_key_missing",
        "desktop_distribution_readiness": "distribution_rc_ready" if developer_id and notary_profile and build_ok else "distribution_blocked_credentials",
        "overall": "distribution_rc_ready" if developer_id and notary_profile and build_ok else "distribution_blocked_credentials" if build_ok else "blocked",
        "blockers": blockers, "developer_id_identity_count": len(identities), "notary_profile_available": notary_profile,
    }


def _software_components() -> list[dict[str, str]]:
    names = ("hydrolite", "streamlit", "pandas", "numpy", "matplotlib", "openpyxl", "pyyaml", "pyinstaller")
    rows = []
    for name in names:
        try: version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: version = "bundled-source" if name == "hydrolite" else "unavailable"
        rows.append({"name": name, "version": version, "source": "Python environment", "license_if_known": "license_metadata_unknown"})
    rows.append({"name": "Sparkle", "version": "2.9.4", "source": "official Sparkle release", "license_if_known": "license_metadata_known"})
    return rows


def write_release_candidate_outputs(app: str | Path, dmg: str | Path, archive: str | Path, output_dir: str | Path, rc_dir: str | Path) -> dict[str, Any]:
    app, dmg, archive, output, dist = map(Path, (app, dmg, archive, output_dir, rc_dir))
    output.mkdir(parents=True, exist_ok=True); dist.mkdir(parents=True, exist_ok=True)
    info = audit_info_plist(app); signing = audit_macos_signature(app); security = audit_desktop_bundle(app)
    architecture = architecture_inventory(app); entitlements = audit_entitlements(app); environment = build_environment()
    zip_audit = audit_zip(archive); readiness = assess_release_readiness(signing, info, security, architecture, zip_audit, entitlements)
    identities = detect_developer_identities()
    spctl = _run(["spctl", "--assess", "--type", "execute", "--verbose=4", str(app)])
    artifacts = [
        {"artifact": app.name, "type": "app", "size": sum(p.stat().st_size for p in app.rglob("*") if p.is_file()), "sha256": hash_app_bundle(app)},
        {"artifact": dmg.name, "type": "dmg", "size": dmg.stat().st_size, "sha256": hash_file(dmg)},
        {"artifact": archive.name, "type": "zip", "size": archive.stat().st_size, "sha256": hash_file(archive)},
    ]
    for row in artifacts:
        row.update({"signed": signing["status"] == "passed", "notarized": False, "stapled": False, "release_included": True, "notes": readiness["overall"]})
    components = _software_components()
    manifest = {
        "product": "HydroLite Studio", "version": info["marketing_version"], "build": int(info["build_number"]),
        "release_channel": "rc", "bundle_id": info["bundle_id"], "architecture": "arm64",
        "minimum_macos": info["minimum_macos"], "git_commit": _run(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "branch": _run(["git", "branch", "--show-current"]).stdout.strip(), "build_time": _now(),
        "build_environment": environment, "python": environment["python"], "pyinstaller": environment["pyinstaller"],
        "swift": environment["swift"], "xcode": environment["xcode"], "sparkle": environment["sparkle"],
        "app_sha256": artifacts[0]["sha256"], "zip_sha256": artifacts[2]["sha256"], "dmg_sha256": artifacts[1]["sha256"],
        "signing_status": signing["signing_mode"], "signing_identity": identities[0] if len(identities) == 1 else "none" if not identities else "selection_required",
        "hardened_runtime": signing["hardened_runtime"], "notarization_status": "credentials_required",
        "staple_status": "not_attempted", "gatekeeper_status": "rejected_pre_notarization" if spctl.returncode else "passed",
        "sparkle_status": "framework_integrated_signing_key_missing" if info["sparkle_public_key"] == "missing" else "configured",
        "update_signing_status": "signing_key_missing" if info["sparkle_public_key"] == "missing" else "public_key_configured_private_key_unverified",
        "test_summary": {"desktop_specialized": "not_run_by_build", "full_pytest": "not_run_by_build", "healthcheck": "not_run_by_build"},
        "known_limitations": readiness["blockers"], "distribution_readiness": readiness["overall"],
    }
    for name, payload in (("desktop_build_environment.json", environment), ("info_plist_audit.json", info), ("nested_code_inventory.json", architecture), ("architecture_inventory.json", architecture), ("entitlements_audit.json", entitlements), ("desktop_release_readiness.json", readiness), ("software_components.json", components)):
        (dist / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest_path = dist / "release_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    artifacts.append({
        "artifact": manifest_path.name, "type": "manifest", "size": manifest_path.stat().st_size,
        "sha256": hash_file(manifest_path), "signed": False, "notarized": False, "stapled": False,
        "release_included": True, "notes": readiness["overall"],
    })
    checksums = "".join(f"{row['sha256']}  {row['artifact']}\n" for row in artifacts if row["type"] != "app")
    (dist / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8")
    pd.DataFrame(artifacts).to_excel(dist / "release_artifact_inventory.xlsx", index=False)
    zh = "# HydroLite Studio 0.7.0 RC1\n\n本候选版整合产品工作台与项目交付治理。当前仅供内部验证；科学状态未因交付审核改变。\n"
    en = "# HydroLite Studio 0.7.0 RC1\n\nThis candidate integrates the product workspace and delivery governance. It is for internal validation; delivery approval does not change scientific status.\n"
    (dist / "release_notes_zh.md").write_text(zh, encoding="utf-8"); (dist / "release_notes_en.md").write_text(en, encoding="utf-8")
    staging = output / "update_staging"; staging.mkdir(parents=True, exist_ok=True)
    (staging / "release_notes_zh.md").write_text(zh, encoding="utf-8"); (staging / "release_notes_en.md").write_text(en, encoding="utf-8")
    appcast = f'''<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel><title>HydroLite Studio RC staging</title><item><title>0.7.0 RC1</title><enclosure url="https://example.invalid/hydrolite/{archive.name}" sparkle:version="{info['build_number']}" sparkle:shortVersionString="0.7.0" length="{archive.stat().st_size}" type="application/octet-stream"/></item></channel></rss>\n'''
    (staging / "appcast.xml").write_text(appcast, encoding="utf-8")
    for language, text in (("zh", zh), ("en", en)):
        (output / f"desktop_release_readiness_{language}.md").write_text(text + f"\n- Readiness: `{readiness['overall']}`\n- Blockers: `{', '.join(readiness['blockers'])}`\n", encoding="utf-8")
    security_safe = {**security, "bundle": app.name}
    diagnostics = {"manifest": manifest, "readiness": readiness, "security": security_safe, "zip_audit": zip_audit, "spctl_return_code": spctl.returncode, "appcast_status": "unsigned_staging_only"}
    (output / "desktop_release_readiness.json").write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding="utf-8")
    return diagnostics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--app", required=True); parser.add_argument("--dmg", required=True); parser.add_argument("--zip", required=True); parser.add_argument("--output", required=True); parser.add_argument("--rc-dir", required=True)
    args = parser.parse_args(argv)
    result = write_release_candidate_outputs(args.app, args.dmg, args.zip, args.output, args.rc_dir)
    print(json.dumps({"status": "passed" if result["readiness"]["build_readiness"] == "internal_rc_ready" else "failed", "readiness": result["readiness"]}, indent=2))
    return 0 if result["readiness"]["build_readiness"] == "internal_rc_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
