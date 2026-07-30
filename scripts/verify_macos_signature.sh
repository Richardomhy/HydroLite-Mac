#!/usr/bin/env bash
set -euo pipefail
APP="${1:?app path required}"
codesign -dvvv --entitlements :- "$APP" 2>&1
codesign --verify --strict --verbose=4 "$APP"
set +e
spctl -a -vv --type execute "$APP" 2>&1
SPCTL=$?
set -e
echo "spctl_return_code=$SPCTL"
