#!/usr/bin/env bash
set -euo pipefail
security find-identity -v -p codesigning 2>&1 || true
if security find-identity -v -p codesigning 2>/dev/null | grep -q "Developer ID Application"; then
  echo "developer_id=available"
else
  echo "developer_id=credentials_required"
fi
