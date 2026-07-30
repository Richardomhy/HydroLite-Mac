from __future__ import annotations

from pathlib import Path
import json
import os
import re


FORBIDDEN_PARTS = {"data_raw", "output", ".git", "tests", "external", "__pycache__"}
FORBIDDEN_SUFFIXES = {".sqlite3", ".dss", ".h5", ".hdf5", ".nc", ".pt", ".pth", ".ckpt", ".onnx", ".p12", ".cer", ".p8", ".key"}
SECRET_NAMES = ("credential", "service-account", "secret", "token", ".netrc", ".cdsapirc")
SECRET_PATTERNS = (
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"(?i)(?:api[_-]?key|client[_-]?secret|private[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}",
)


def audit_desktop_bundle(bundle_path: str | Path) -> dict:
    root = Path(bundle_path).resolve()
    findings = []
    if not root.exists():
        findings.append({"severity": "high", "path": str(root), "message": "App bundle is missing"})
    for path in root.rglob("*") if root.exists() else []:
        relative = path.relative_to(root)
        lower = relative.as_posix().lower()
        if set(relative.parts) & FORBIDDEN_PARTS or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append({"severity": "high", "path": relative.as_posix(), "message": "Forbidden bundle content"})
        if "_internal" not in relative.parts and any(name in lower for name in SECRET_NAMES):
            findings.append({"severity": "high", "path": relative.as_posix(), "message": "Potential secret material"})
        if path.is_file() and os.access(path, os.X_OK) and path.stat().st_mode & 0o002:
            findings.append({"severity": "high", "path": relative.as_posix(), "message": "World-writable executable"})
        if path.is_file() and path.stat().st_size < 2_000_000 and path.suffix.lower() in {".py", ".sh", ".json", ".yaml", ".yml", ".toml", ".plist"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "shell=True" in text:
                findings.append({"severity": "high", "path": relative.as_posix(), "message": "shell=True found"})
            if re.search(r"/Users/[^/\\s]+/", text):
                findings.append({"severity": "medium", "path": relative.as_posix(), "message": "User absolute path found"})
            if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
                findings.append({"severity": "high", "path": relative.as_posix(), "message": "Potential embedded private credential"})
    high = [item for item in findings if item["severity"] == "high"]
    return {"status": "passed" if not high else "failed", "bundle": str(root), "findings": findings, "high_risk_count": len(high), "developer_id_gate": not high}


def write_security_audit(output_dir: str | Path, result: dict) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    json_path, md_path = output / "security_audit.json", output / "security_audit.md"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md_path.write_text(f"# Desktop Security Audit\n\n- Status: `{result['status']}`\n- High risk findings: `{result['high_risk_count']}`\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
