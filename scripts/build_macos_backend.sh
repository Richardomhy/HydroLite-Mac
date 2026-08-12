#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${HYDROLITE_DESKTOP_OUTPUT:-$ROOT/output/macos_packaging}"
DIST="${HYDROLITE_BACKEND_DIST:-$ROOT/build/macos/backend}"
WORK="${HYDROLITE_PYINSTALLER_WORK:-$ROOT/build/macos/pyinstaller}"
mkdir -p "$OUT" "$DIST" "$WORK"
PY="${HYDROLITE_BUILD_PYTHON:-$(conda info --base)/envs/hydrolite-build/bin/python}"
"$PY" -m PyInstaller --clean --noconfirm \
  --distpath "$DIST" \
  --workpath "$WORK" \
  "$ROOT/packaging/macos/hydrolite_backend.spec"
find "$DIST/hydrolite-backend/_internal" -type d -name tests -prune -exec rm -rf {} +
EXE="$DIST/hydrolite-backend/hydrolite-backend"
test -x "$EXE"
cat > "$OUT/backend_build_report.md" <<EOF
# Backend Build Report

- Status: success
- Mode: PyInstaller onedir
- Executable: \`$EXE\`
- Architecture: \`$(file "$EXE")\`
EOF
