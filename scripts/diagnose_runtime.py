#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hydrolite.deployment import build_deployment_manifest, write_deployment_report
from hydrolite.runtime_db import get_database_version, initialize_runtime_database
from hydrolite.runtime_paths import get_runtime_root


def main() -> int:
    initialize_runtime_database()
    result = build_deployment_manifest()
    result["database_version"] = get_database_version()
    outputs = write_deployment_report(get_runtime_root() / "reports", result)
    print(json.dumps({"status": "passed", "outputs": {key: str(value) for key, value in outputs.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
