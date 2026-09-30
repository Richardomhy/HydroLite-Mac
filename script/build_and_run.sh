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
    VERIFY_STARTED_AT="$(date +%s)"
    open_app
    for _ in {1..60}; do
      MANIFEST="$HOME/Library/Application Support/HydroLite Studio/backend_manifest.json"
      APP_PID="$(pgrep -x "$APP_NAME" | head -n 1 || true)"
      if [[ -n "$APP_PID" && -f "$MANIFEST" && "$(stat -f %m "$MANIFEST" 2>/dev/null || echo 0)" -ge "$VERIFY_STARTED_AT" ]]; then
        BACKEND_INFO="$(/usr/bin/python3 -c 'import json,sys,urllib.parse; m=json.load(open(sys.argv[1])); u=urllib.parse.urlsplit(m.get("url", "")); assert m.get("address")=="127.0.0.1" and u.scheme=="http" and u.hostname=="127.0.0.1" and u.port==int(m["port"]) and 0<int(m["port"])<65536 and int(m["pid"])>0; print("%s\t%s\t%s" % (m["pid"],m["port"],m["url"]))' "$MANIFEST" 2>/dev/null || true)"
        if [[ -n "$BACKEND_INFO" ]]; then
          IFS=$'\t' read -r BACKEND_PID BACKEND_PORT URL <<< "$BACKEND_INFO"
          BACKEND_PARENT="$(ps -o ppid= -p "$BACKEND_PID" 2>/dev/null | tr -d ' ' || true)"
          if kill -0 "$BACKEND_PID" 2>/dev/null && [[ "$BACKEND_PARENT" == "$APP_PID" ]] && curl -fsS --max-time 1 "$URL/_stcore/health" 2>/dev/null | grep -q '^ok$'; then
            echo "Desktop ready: app=$APP_PID backend=$BACKEND_PID port=$BACKEND_PORT manifest=$MANIFEST"
            exit 0
          fi
        fi
      fi
      sleep 1
    done
    echo "HydroLite Studio backend failed validation: app/backend parent, fresh manifest, loopback URL, or health check not ready" >&2
    exit 1
    ;;
  *)
    echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2
    exit 2
    ;;
esac
