#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/scripts/macos_xcode_env.sh"
PKG="$ROOT/desktop/macos/HydroLiteStudio"
OUT="$ROOT/output/macos_packaging"
mkdir -p "$OUT" "$ROOT/build/macos/shell"
VENDOR="$PKG/.build/vendor"
SPARKLE="$VENDOR/Sparkle.xcframework"
if [[ ! -d "$SPARKLE" ]]; then
  ARCHIVE="$VENDOR/Sparkle-for-Swift-Package-Manager-2.9.4.zip"
  mkdir -p "$VENDOR"
  curl -fL --retry 5 --connect-timeout 20 --max-time 600 \
    -o "$ARCHIVE" \
    https://github.com/sparkle-project/Sparkle/releases/download/2.9.4/Sparkle-for-Swift-Package-Manager.zip
  echo "cb6fdbdc8884f15d62a616e79face92b08322410fd2d425edc6596ccbf4ba3b0  $ARCHIVE" | shasum -a 256 -c -
  unzip -q "$ARCHIVE" "Sparkle.xcframework/*" -d "$VENDOR"
fi
swift build --package-path "$PKG" -c release
cp "$PKG/.build/release/HydroLiteStudio" "$ROOT/build/macos/shell/HydroLiteStudio"
cat > "$OUT/shell_build_report.md" <<EOF
# Swift Shell Build Report

- Status: success
- Swift: \`$(swift --version | head -1)\`
- Architecture: \`$(file "$ROOT/build/macos/shell/HydroLiteStudio")\`
EOF
