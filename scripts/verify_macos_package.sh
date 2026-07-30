#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DMG="${1:-$ROOT/dist/macos/HydroLite-Studio-0.7.0-arm64.dmg}"
MOUNT="$(mktemp -d /tmp/hydrolite-dmg.XXXXXX)"
cleanup() { hdiutil detach "$MOUNT" -quiet 2>/dev/null || true; rmdir "$MOUNT" 2>/dev/null || true; }
trap cleanup EXIT
hdiutil attach "$DMG" -mountpoint "$MOUNT" -nobrowse -quiet
test -d "$MOUNT/HydroLite-Studio-0.7.0-arm64.app"
test -L "$MOUNT/Applications"
echo "package verification passed"
