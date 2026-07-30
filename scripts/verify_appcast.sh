#!/usr/bin/env bash
set -euo pipefail
python - "${1:?appcast path required}" <<'PY'
from xml.etree import ElementTree
import sys
root = ElementTree.parse(sys.argv[1]).getroot()
assert root.tag == "rss"
print("appcast valid")
PY
