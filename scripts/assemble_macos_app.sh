#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${HYDROLITE_APP_PATH:-$ROOT/dist/macos/HydroLite-Studio-0.7.0-arm64.app}"
BACKEND="$ROOT/build/macos/backend/hydrolite-backend"
SHELL="$ROOT/build/macos/shell/HydroLiteStudio"
test -x "$BACKEND/hydrolite-backend"
test -x "$SHELL"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/backend"
cp "$SHELL" "$APP/Contents/MacOS/HydroLite Studio"
cp -R "$BACKEND" "$APP/Contents/Resources/backend/"
cp "$ROOT/desktop/macos/HydroLiteStudio/Resources/Info.plist" "$APP/Contents/Info.plist"
BUILD="${HYDROLITE_BUILD_NUMBER:-$(git -C "$ROOT" rev-list --count HEAD)}"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD" "$APP/Contents/Info.plist"
cat > "$APP/Contents/Resources/version.json" <<EOF
{"app_name":"HydroLite Studio","version":"0.7.0-dev","short_version":"0.7.0","build_number":"$BUILD","channel":"dev"}
EOF
mkdir -p "$ROOT/output/macos_packaging"
"${HYDROLITE_BUILD_PYTHON:-$(conda info --base)/envs/hydrolite-build/bin/python}" - "$APP" "$ROOT/output/macos_packaging" <<'PY'
from pathlib import Path
import sys
from hydrolite.desktop.bundle_resources import validate_bundle_resources, write_bundle_resource_report
root = Path(sys.argv[1]) / "Contents" / "Resources" / "backend" / "hydrolite-backend"
write_bundle_resource_report(sys.argv[2], validate_bundle_resources(root))
PY
echo "$APP"
