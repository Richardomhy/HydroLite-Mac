from __future__ import annotations

from pathlib import Path
import json
import subprocess

import pandas as pd


def detect_developer_identities() -> list[str]:
    result = subprocess.run(["security", "find-identity", "-p", "codesigning", "-v"], capture_output=True, text=True, check=False, timeout=15)
    return [line.strip() for line in result.stdout.splitlines() if "Developer ID Application" in line]


def inventory_macho_files(app_path: str | Path) -> list[dict]:
    root = Path(app_path)
    rows = []
    for path in root.rglob("*") if root.exists() else []:
        if not path.is_file():
            continue
        kind = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True, errors="replace", check=False, timeout=5).stdout.strip()
        if "Mach-O" not in kind:
            continue
        signature = subprocess.run(["codesign", "-dv", "--verbose=2", str(path)], capture_output=True, text=True, errors="replace", check=False, timeout=10)
        rows.append({"path": str(path.relative_to(root)), "architecture": kind, "signed": signature.returncode == 0, "signature": (signature.stderr or signature.stdout)[-1000:]})
    return rows


def audit_macos_signature(app_path: str | Path) -> dict:
    app = Path(app_path)
    verify = subprocess.run(["codesign", "--verify", "--strict", "--verbose=4", str(app)], capture_output=True, text=True, errors="replace", check=False, timeout=30) if app.exists() else None
    details = subprocess.run(["codesign", "-dvvv", "--entitlements", ":-", str(app)], capture_output=True, text=True, errors="replace", check=False, timeout=30) if app.exists() else None
    inventory = inventory_macho_files(app)
    text = (details.stderr + details.stdout) if details else ""
    return {
        "status": "passed" if verify and verify.returncode == 0 and all(item["signed"] for item in inventory) else "failed",
        "app": str(app), "verify_return_code": verify.returncode if verify else None,
        "verify_output": ((verify.stderr or verify.stdout)[-4000:] if verify else "app missing"),
        "signing_mode": "developer_id" if "Developer ID Application" in text else "ad_hoc" if "Signature=adhoc" in text else "unsigned",
        "team_id": next((line.split("=", 1)[1] for line in text.splitlines() if line.startswith("TeamIdentifier=")), ""),
        "hardened_runtime": "flags=0x10000(runtime)" in text,
        "get_task_allow": "com.apple.security.get-task-allow" in text,
        "macho_inventory": inventory,
    }


def write_signing_audit(output_dir: str | Path, result: dict) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    json_path, md_path, xlsx_path = output / "signing_audit.json", output / "signing_audit.md", output / "macho_inventory.xlsx"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md_path.write_text(f"# Signing Audit\n\n- Status: `{result['status']}`\n- Mode: `{result['signing_mode']}`\n- Hardened runtime: `{result['hardened_runtime']}`\n- get-task-allow: `{result['get_task_allow']}`\n", encoding="utf-8")
    pd.DataFrame(result["macho_inventory"]).to_excel(xlsx_path, index=False)
    return {"json": json_path, "markdown": md_path, "xlsx": xlsx_path}
