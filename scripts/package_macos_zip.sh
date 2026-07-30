#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/dist/macos"
APP="$DIR/HydroLite-Studio-0.7.0-arm64.app"
ZIP="$DIR/HydroLite-Studio-0.7.0-arm64.zip"
test -d "$APP"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
shasum -a 256 "$ZIP" > "$DIR/SHA256SUMS"
echo "$ZIP"
