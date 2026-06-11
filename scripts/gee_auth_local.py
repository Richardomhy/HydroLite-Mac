from __future__ import annotations

from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from hydrolite.gee.auth import detect_gee_credentials, initialize_gee


OUTPUT_PATH = PROJECT_ROOT / "output" / "gee_auth_local_report.txt"


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    credentials = detect_gee_credentials()
    init = initialize_gee()
    report = {
        "credentials_detected": credentials,
        "initialization": init,
        "local_auth_command": "python -c \"import ee; ee.Authenticate()\"",
        "initialize_test_command": "python -c \"import ee; ee.Initialize(project='your-project-id'); print('ok')\"",
        "project_env_command": "export GEE_PROJECT=\"your-gee-project-id\"",
        "security_note": "This script does not write credentials into the project directory. Do not commit ~/.config/earthengine, service account JSON, or .streamlit/secrets.toml.",
    }
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote GEE local auth report to: {OUTPUT_PATH}")
    if init["status"] != "available":
        print("GEE is not initialized yet. Run:")
        print("python -c \"import ee; ee.Authenticate()\"")
        print("export GEE_PROJECT=\"your-gee-project-id\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
