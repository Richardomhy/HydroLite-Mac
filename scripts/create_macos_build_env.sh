#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="hydrolite-build"
OUT="$ROOT/output/macos_packaging"
mkdir -p "$OUT"

command -v conda >/dev/null || { echo "conda is required"; exit 1; }
if ! conda env list --json | python -c "import json,sys; print(any(p.endswith('/$ENV_NAME') for p in json.load(sys.stdin)['envs']))" | grep -q True; then
  conda create -n "$ENV_NAME" python=3.12 -y
fi

conda run -n "$ENV_NAME" python -m pip install --upgrade pip setuptools wheel
conda run -n "$ENV_NAME" python -m pip install \
  "matplotlib>=3.8" "openpyxl>=3.1" "pandas>=2.0" "python-docx>=1.1" \
  "PyYAML>=6.0" "streamlit>=1.58" "psutil>=5.9" "packaging>=24" "pyinstaller>=6.10"
conda run -n "$ENV_NAME" python -m pip install --no-deps -e "$ROOT"
conda run -n "$ENV_NAME" python -c "import hydrolite,streamlit,PyInstaller,pandas; print('desktop build imports: ok')"

conda run -n "$ENV_NAME" python -m pip freeze \
  | sed -E "s#^-e .*#hydrolite-mac==0.7.0.dev0#" \
  | grep -Ev '(/Users/|file://)' >"$OUT/requirements_lock.txt"

cat >"$OUT/conda_environment.yml" <<'EOF'
name: hydrolite-build
channels:
  - conda-forge
dependencies:
  - python=3.12
  - pip
  - pip:
      - -e .[desktop,desktop-build,desktop-update]
EOF

conda run -n "$ENV_NAME" python "$ROOT/scripts/diagnose_macos_build_env.py"
