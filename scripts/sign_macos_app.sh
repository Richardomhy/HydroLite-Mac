#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-ad_hoc}"
APP="${HYDROLITE_APP_PATH:-$ROOT/dist/macos/HydroLite-Studio-0.7.0-arm64.app}"
ENT="$ROOT/packaging/macos/HydroLiteStudio.entitlements"
test -d "$APP"
case "$MODE" in
  ad_hoc) IDENTITY="-"; OPTIONS=(--timestamp=none) ;;
  developer_id)
    : "${HYDROLITE_CODESIGN_IDENTITY:?credentials_required: set HYDROLITE_CODESIGN_IDENTITY}"
    IDENTITY="$HYDROLITE_CODESIGN_IDENTITY"
    security find-identity -v -p codesigning | grep -F "$IDENTITY" >/dev/null || { echo "credentials_required: identity not found"; exit 78; }
    OPTIONS=(--timestamp --options runtime)
    ;;
  unsigned) echo "unsigned requested"; exit 0 ;;
  *) echo "mode must be unsigned, ad_hoc, or developer_id"; exit 64 ;;
esac
while IFS= read -r -d '' file; do
  if file "$file" | grep -q "Mach-O"; then
    codesign --force --sign "$IDENTITY" "${OPTIONS[@]}" "$file"
  fi
done < <(find "$APP/Contents" -type f -print0)
codesign --force --sign "$IDENTITY" "${OPTIONS[@]}" --entitlements "$ENT" "$APP"
bash "$ROOT/scripts/verify_macos_signature.sh" "$APP"
