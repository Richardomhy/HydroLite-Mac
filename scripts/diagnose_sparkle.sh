#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/output/macos_packaging/update_readiness_report.md"
mkdir -p "$(dirname "$OUT")"
cat > "$OUT" <<EOF
# Update Readiness

- Sparkle framework: not integrated
- Feed: not configured
- Readiness: framework_ready_configuration_missing
- Manual HTTPS release-manifest fallback: available
- Private update key in repository: no
EOF
cat "$OUT"
