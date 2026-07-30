#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/scripts/macos_xcode_env.sh"
APP="${HYDROLITE_APP_PATH:-$ROOT/dist/macos/HydroLite-Studio-0.7.0-arm64.app}"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
