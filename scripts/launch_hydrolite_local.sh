#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${HYDROLITE_RUNTIME_DIR:-$HOME/.hydrolite/runtime}"
PID_FILE="$RUNTIME_DIR/locks/streamlit.pid"
LOG_FILE="$RUNTIME_DIR/logs/streamlit.log"
PORT="${HYDROLITE_PORT:-8501}"

mkdir -p "$RUNTIME_DIR/locks" "$RUNTIME_DIR/logs"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "HydroLite Streamlit already running with PID $(cat "$PID_FILE")"
  exit 0
fi

cd "$ROOT"
python -m hydrolite runtime init >/dev/null
nohup python -m streamlit run streamlit_app.py \
  --server.headless true \
  --server.address 127.0.0.1 \
  --server.port "$PORT" >"$LOG_FILE" 2>&1 &
PID=$!
printf '%s\n' "$PID" >"$PID_FILE"
sleep 2
if ! kill -0 "$PID" 2>/dev/null; then
  echo "HydroLite Streamlit failed to start. See $LOG_FILE"
  exit 1
fi
echo "HydroLite Streamlit started: http://127.0.0.1:$PORT (PID $PID)"
