#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/desktop/macos/HydroLiteStudio"
OUT="$ROOT/output/macos_packaging"
mkdir -p "$OUT" "$ROOT/build/macos/shell"
swift build --package-path "$PKG" -c release
cp "$PKG/.build/release/HydroLiteStudio" "$ROOT/build/macos/shell/HydroLiteStudio"
cat > "$OUT/shell_build_report.md" <<EOF
# Swift Shell Build Report

- Status: success
- Swift: \`$(swift --version | head -1)\`
- Architecture: \`$(file "$ROOT/build/macos/shell/HydroLiteStudio")\`
EOF
