#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${HYDROLITE_RUNTIME_DIR:-$HOME/.hydrolite/runtime}"
PID_FILE="$RUNTIME_DIR/locks/streamlit.pid"
if [[ ! -f "$PID_FILE" ]]; then
  echo "No HydroLite Streamlit PID file found."
  exit 0
fi

PID="$(cat "$PID_FILE")"
COMMAND="$(ps -p "$PID" -o command= 2>/dev/null || true)"
if [[ "$COMMAND" != *"streamlit run streamlit_app.py"* ]]; then
  echo "PID $PID is not the recorded HydroLite Streamlit command; refusing to stop it."
  exit 1
fi
kill -TERM "$PID"
for _ in {1..20}; do
  kill -0 "$PID" 2>/dev/null || break
  sleep 0.25
done
if kill -0 "$PID" 2>/dev/null; then
  echo "HydroLite Streamlit did not stop cleanly."
  exit 1
fi
rm -f "$PID_FILE"
echo "HydroLite Streamlit stopped: PID $PID"
