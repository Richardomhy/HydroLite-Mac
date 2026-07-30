from __future__ import annotations

from pathlib import Path
import json
import os
import plistlib
import shutil
import subprocess
import sys
import zipfile

from hydrolite.desktop.bundle_resources import validate_bundle_resources, write_bundle_resource_report
from hydrolite.desktop.desktop_diagnosis import write_desktop_diagnosis
from hydrolite.desktop.desktop_update import inspect_update_status
from hydrolite.desktop.security_audit import audit_desktop_bundle, write_security_audit
from hydrolite.desktop.signing_audit import audit_macos_signature, write_signing_audit
from hydrolite.release_metadata import build_release_manifest, write_release_metadata

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "macos_packaging"
APP = ROOT / "dist" / "macos" / "HydroLite-Studio-0.7.0-arm64.app"


def _run(script: str, *args: str) -> int:
    return subprocess.run(["bash", str(ROOT / "scripts" / script), *args], cwd=ROOT, check=False).returncode


def run_desktop_command(command: str, mode: str | None = None) -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if command in {"diagnose", "build-env"}:
        result = write_desktop_diagnosis(OUTPUT)
        print(json.dumps({key: str(value) for key, value in result.items()}, indent=2))
        return 0
    if command == "resources":
        root = APP / "Contents" / "Resources" / "backend" / "hydrolite-backend"
        result = write_bundle_resource_report(OUTPUT, validate_bundle_resources(root))
        print(json.dumps({key: str(value) for key, value in result.items()}, indent=2))
        return 0
    scripts = {
        "build-backend": "build_macos_backend.sh",
        "build-shell": "build_macos_shell.sh",
        "assemble": "assemble_macos_app.sh",
        "build": "build_macos_app.sh",
        "package-zip": "package_macos_zip.sh",
        "package-dmg": "package_macos_dmg.sh",
        "signing-status": "detect_macos_signing.sh",
    }
    if command in scripts:
        return _run(scripts[command])
    if command == "launch":
        return subprocess.run(["open", "-n", str(APP)], check=False).returncode
    if command == "verify":
        code = _run("verify_macos_signature.sh", str(APP))
        result = write_desktop_diagnosis(OUTPUT, APP)
        print(json.dumps({key: str(value) for key, value in result.items()}, indent=2))
        return code
    if command == "security-audit":
        result = audit_desktop_bundle(APP)
        write_security_audit(OUTPUT, result)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "passed" else 1
    if command == "sign":
        return _run("sign_macos_app.sh", mode or "ad_hoc")
    if command in {"notarization-gate", "notarize"}:
        return _run("notarize_macos_app.sh", mode or "dry-run")
    if command == "staple":
        return _run("staple_macos_app.sh")
    if command == "update-status":
        _run("diagnose_sparkle.sh")
        print(json.dumps(inspect_update_status(ROOT / "packaging" / "macos" / "update_config.example.json"), indent=2))
        return 0
    if command == "appcast":
        return _run("generate_appcast.sh", mode or "dry-run")
    if command in {"report", "validate"}:
        return write_release_reports(validate=command == "validate")
    raise ValueError(f"Unsupported desktop command: {command}")


def write_release_reports(validate: bool = False) -> int:
    security = audit_desktop_bundle(APP)
    write_security_audit(OUTPUT, security)
    signing = audit_macos_signature(APP)
    write_signing_audit(OUTPUT, signing)
    plist_path = APP / "Contents" / "Info.plist"
    info = plistlib.loads(plist_path.read_bytes()) if plist_path.exists() else {}
    manifest = build_release_manifest(
        version="0.7.0-dev",
        build_number=int(info.get("CFBundleVersion", 0)),
        artifacts=[str(path) for path in (APP, ROOT / "dist" / "macos" / "HydroLite-Studio-0.7.0-arm64.zip", ROOT / "dist" / "macos" / "HydroLite-Studio-0.7.0-arm64.dmg") if path.exists()],
        signing=signing,
        security=security,
    )
    write_release_metadata(OUTPUT, manifest)
    shutil.copy2(OUTPUT / "release_manifest.json", ROOT / "dist" / "macos" / "release_manifest.json")
    reports = {
        "app": str(APP),
        "development_bundle": APP.exists(),
        "local_ad_hoc_app": signing.get("signing_mode") == "ad_hoc" and signing.get("status") == "passed",
        "developer_id_signed": "credentials_required",
        "notarized_distribution": "credentials_required",
        "security_status": security["status"],
        "update_readiness": "framework_ready_configuration_missing",
    }
    for language, title in (("zh", "macOS 发行报告"), ("en", "macOS Release Report")):
        path = OUTPUT / f"macos_release_report_{language}.md"
        path.write_text(f"# {title}\n\n```json\n{json.dumps(reports, indent=2, ensure_ascii=False)}\n```\n", encoding="utf-8")
    (OUTPUT / "packaging_report.md").write_text(
        "# macOS Packaging Report\n\n"
        f"- App: `{APP}`\n"
        f"- ZIP: `{ROOT / 'dist/macos/HydroLite-Studio-0.7.0-arm64.zip'}`\n"
        f"- DMG: `{ROOT / 'dist/macos/HydroLite-Studio-0.7.0-arm64.dmg'}`\n"
        f"- Security: `{security['status']}`\n"
        f"- Signing: `{signing['signing_mode']}`\n",
        encoding="utf-8",
    )
    bundle_files = [path for path in OUTPUT.iterdir() if path.suffix in {".md", ".json", ".xlsx", ".txt"}]
    with zipfile.ZipFile(OUTPUT / "macos_packaging_bundle.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in bundle_files:
            archive.write(path, path.name)
    (OUTPUT / "macos_packaging_manifest.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2, ensure_ascii=False))
    if validate and (not APP.exists() or security["status"] != "passed"):
        return 1
    return 0
