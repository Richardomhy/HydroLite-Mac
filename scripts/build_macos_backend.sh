#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/output/macos_packaging"
mkdir -p "$OUT" "$ROOT/build/macos"
PY="${HYDROLITE_BUILD_PYTHON:-$(conda info --base)/envs/hydrolite-build/bin/python}"
"$PY" -m PyInstaller --clean --noconfirm \
  --distpath "$ROOT/build/macos/backend" \
  --workpath "$ROOT/build/macos/pyinstaller" \
  "$ROOT/packaging/macos/hydrolite_backend.spec"
find "$ROOT/build/macos/backend/hydrolite-backend/_internal" -type d -name tests -prune -exec rm -rf {} +
EXE="$ROOT/build/macos/backend/hydrolite-backend/hydrolite-backend"
test -x "$EXE"
cat > "$OUT/backend_build_report.md" <<EOF
# Backend Build Report

- Status: success
- Mode: PyInstaller onedir
- Executable: \`$EXE\`
- Architecture: \`$(file "$EXE")\`
EOF
