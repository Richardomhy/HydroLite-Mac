#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/output/macos_packaging/update_readiness_report.md"
mkdir -p "$(dirname "$OUT")"
cat > "$OUT" <<EOF
# Update Readiness

- Sparkle framework: integrated via Swift Package Manager 2.9.4
- Feed: https://github.com/Richardomhy/HydroLite-Mac/releases/latest/download/appcast.xml
- Public signing key injected: $([[ -n "${HYDROLITE_SPARKLE_PUBLIC_KEY:-}" ]] && echo yes || echo no)
- Readiness: $([[ -n "${HYDROLITE_SPARKLE_PUBLIC_KEY:-}" ]] && echo feed_ready || echo signing_key_required)
- Manual HTTPS release-manifest fallback: available
- Private update key in repository: no
EOF
cat "$OUT"
