from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from hydrolite.openhydronet.runner import run_openhydronet_smoke


def main() -> int:
    result = run_openhydronet_smoke(PROJECT_ROOT / "configs" / "openhydronet.example.yaml")
    print(f"OpenHydroNet smoke status: {result['status']}")
    print(f"Summary: {result['summary_path']}")
    print(f"Report: {result['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
