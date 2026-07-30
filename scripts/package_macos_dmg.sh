#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/dist/macos"
APP="$DIR/HydroLite-Studio-0.7.0-arm64.app"
DMG="$DIR/HydroLite-Studio-0.7.0-arm64.dmg"
STAGE="$ROOT/build/macos/dmg"
test -d "$APP"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
printf 'Drag HydroLite Studio to Applications. This dev build is ad-hoc signed.\n' > "$STAGE/README.txt"
hdiutil create -volname "HydroLite Studio 0.7.0-dev" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
shasum -a 256 "$DMG" >> "$DIR/SHA256SUMS"
echo "$DMG"
