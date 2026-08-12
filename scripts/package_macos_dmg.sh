#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${HYDROLITE_RC_DIR:-$ROOT/dist/macos}"
APP="${HYDROLITE_APP_PATH:-$DIR/HydroLite-Studio-0.7.0-arm64.app}"
DMG="${HYDROLITE_DMG_PATH:-${APP%.app}.dmg}"
STAGE="${HYDROLITE_DMG_STAGE:-$ROOT/build/macos/dmg}"
test -d "$APP"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/$(basename "$APP")"
ln -s /Applications "$STAGE/Applications"
printf 'Drag HydroLite Studio to Applications. This release candidate is for internal validation until distribution credentials pass.\n' > "$STAGE/README.txt"
hdiutil create -volname "HydroLite Studio 0.7.0 RC1" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
shasum -a 256 "$DMG" >> "$DIR/SHA256SUMS.txt"
echo "$DMG"
