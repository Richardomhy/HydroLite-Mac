#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${HYDROLITE_RC_DIR:-$ROOT/dist/macos}"
APP="${HYDROLITE_APP_PATH:-$DIR/HydroLite-Studio-0.7.0-arm64.app}"
ZIP="${HYDROLITE_ZIP_PATH:-${APP%.app}.zip}"
test -d "$APP"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
shasum -a 256 "$ZIP" > "$DIR/SHA256SUMS.txt"
echo "$ZIP"
