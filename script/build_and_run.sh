#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
APP_NAME="HydroLite Studio"
BUNDLE_ID="com.hydrolite.studio"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$ROOT/desktop/macos/HydroLiteStudio"
APP="$ROOT/build/macos/debug/HydroLite Studio.app"
SHELL_OUT="$ROOT/build/macos/shell-debug/HydroLiteStudio"
BACKEND="$ROOT/build/macos/backend/hydrolite-backend"

wait_for_shutdown() {
  for _ in {1..10}; do
    if ! pgrep -x "$APP_NAME" >/dev/null && ! pgrep -x hydrolite-backend >/dev/null; then
      return 0
    fi
    sleep 1
  done
  pkill -KILL -x "$APP_NAME" >/dev/null 2>&1 || true
  pkill -KILL -x hydrolite-backend >/dev/null 2>&1 || true
  for _ in {1..5}; do
    if ! pgrep -x "$APP_NAME" >/dev/null && ! pgrep -x hydrolite-backend >/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "Previous HydroLite Studio process did not exit" >&2
  return 1
}

pkill -x "$APP_NAME" >/dev/null 2>&1 || true
pkill -x hydrolite-backend >/dev/null 2>&1 || true
wait_for_shutdown
. "$ROOT/scripts/macos_xcode_env.sh"

if [[ ! -x "$BACKEND/hydrolite-backend" ]] || find "$ROOT/hydrolite" "$ROOT/streamlit_app.py" "$ROOT/packaging/macos" -type f -newer "$BACKEND/hydrolite-backend" -print -quit | grep -q .; then
  "$ROOT/scripts/build_macos_backend.sh"
fi
if [[ ! -d "$PKG/.build/vendor/Sparkle.xcframework" ]]; then
  "$ROOT/scripts/build_macos_shell.sh"
fi
swift build --package-path "$PKG" -c debug
mkdir -p "$(dirname "$SHELL_OUT")"
cp "$PKG/.build/debug/HydroLiteStudio" "$SHELL_OUT"
HYDROLITE_APP_PATH="$APP" \
HYDROLITE_BACKEND_DIR="$BACKEND" \
HYDROLITE_SHELL_OUTPUT="$SHELL_OUT" \
HYDROLITE_DESKTOP_OUTPUT="$ROOT/output/m8a_desktop" \
HYDROLITE_SKIP_STRIP=1 \
"$ROOT/scripts/assemble_macos_app.sh" >/dev/null

open_app() { /usr/bin/open -n "$APP"; }

case "$MODE" in
  run)
    open_app
    ;;
  --debug|debug)
    lldb -- "$APP/Contents/MacOS/$APP_NAME"
    ;;
  --logs|logs)
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
    ;;
  --telemetry|telemetry)
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify|verify)
    open_app
    for _ in {1..60}; do
      MANIFEST="$HOME/Library/Application Support/HydroLite Studio/backend_manifest.json"
      if pgrep -x "$APP_NAME" >/dev/null && [[ -f "$MANIFEST" ]]; then
        URL="$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["url"])' "$MANIFEST" 2>/dev/null || true)"
        [[ -n "$URL" ]] && curl -fsS "$URL/_stcore/health" | grep -q ok && exit 0
      fi
      sleep 1
    done
    echo "HydroLite Studio process or backend manifest did not become ready" >&2
    exit 1
    ;;
  *)
    echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2
    exit 2
    ;;
esac
