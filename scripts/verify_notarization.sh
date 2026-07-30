#!/usr/bin/env bash
set -euo pipefail
APP="${1:?app path required}"
xcrun stapler validate "$APP"
spctl -a -vv --type execute "$APP"
