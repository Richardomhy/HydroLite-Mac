from __future__ import annotations

from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from hydrolite.openhydronet.diagnostics import build_openhydronet_diagnosis

OUTPUT_PATH = PROJECT_ROOT / "output" / "openhydronet_diagnosis.txt"


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    diagnosis = build_openhydronet_diagnosis()
    OUTPUT_PATH.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote OpenHydroNet diagnosis to: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
