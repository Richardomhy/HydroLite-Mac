#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/scripts/macos_xcode_env.sh"
APP="${1:?app path required}"
xcrun stapler validate "$APP"
spctl -a -vv --type execute "$APP"
