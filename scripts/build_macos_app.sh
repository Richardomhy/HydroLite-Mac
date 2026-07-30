#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
test -x "$ROOT/build/macos/backend/hydrolite-backend/hydrolite-backend" || bash "$ROOT/scripts/build_macos_backend.sh"
test -x "$ROOT/build/macos/shell/HydroLiteStudio" || bash "$ROOT/scripts/build_macos_shell.sh"
bash "$ROOT/scripts/assemble_macos_app.sh"
bash "$ROOT/scripts/sign_macos_app.sh" ad_hoc
