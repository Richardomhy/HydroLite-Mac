#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/scripts/macos_xcode_env.sh"
MODE="${1:-dry-run}"
ZIP="${HYDROLITE_ZIP_PATH:-$ROOT/dist/macos/HydroLite-Studio-0.7.0-arm64.zip}"
OUT="$ROOT/output/macos_packaging/notarization_report.md"
mkdir -p "$(dirname "$OUT")"
if [[ "$MODE" != "--execute" && "$MODE" != "execute" ]]; then
  STATUS="credentials_required"
  [[ -n "${HYDROLITE_NOTARY_PROFILE:-}" ]] && STATUS="not_attempted"
  printf '# Notarization Report\n\n- Mode: dry-run\n- Status: `%s`\n- Upload performed: no\n' "$STATUS" > "$OUT"
  echo "$STATUS"
  exit 0
fi
[[ -n "${HYDROLITE_NOTARY_PROFILE:-}" ]] || { echo "credentials_required: set HYDROLITE_NOTARY_PROFILE keychain profile"; exit 78; }
test -f "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile "$HYDROLITE_NOTARY_PROFILE" --wait
printf '# Notarization Report\n\n- Status: `submitted`\n' > "$OUT"
