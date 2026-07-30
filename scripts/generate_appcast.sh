#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-dry-run}"
[[ "$MODE" == "dry-run" || "$MODE" == "--dry-run" ]] || { echo "Only dry-run is supported until a signed HTTPS feed is configured."; exit 78; }
python - "$ROOT/packaging/macos/appcast.example.xml" <<'PY'
from pathlib import Path
from xml.etree import ElementTree
import sys
ElementTree.parse(sys.argv[1])
print(f"appcast dry-run passed: {Path(sys.argv[1])}")
PY
