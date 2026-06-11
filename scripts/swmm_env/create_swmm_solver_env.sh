#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="$ROOT_DIR/output"
DIAG="$OUT_DIR/swmm_solver_env_diagnosis.txt"
ENV_NAME="hydrolite-swmm-x64"

mkdir -p "$OUT_DIR"
: > "$DIAG"

log() {
  echo "$*" | tee -a "$DIAG"
}

log "HydroLite SWMM isolated solver environment setup"
log "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
log "macOS=$(sw_vers 2>/dev/null | tr '\n' '; ' || true)"
ARCH="$(uname -m)"
SHELL_ARCH="$(arch 2>/dev/null || uname -m)"
log "cpu_architecture=$ARCH"
log "current_shell_architecture=$SHELL_ARCH"

if command -v conda >/dev/null 2>&1; then
  CONDA_BIN="$(command -v conda)"
  CONDA_BASE="$(conda info --base 2>/dev/null || true)"
  log "conda_available=true"
  log "conda_bin=$CONDA_BIN"
  log "conda_base=$CONDA_BASE"
else
  log "conda_available=false"
  log "Cannot create isolated SWMM environment: conda not found."
  exit 0
fi

if [[ "$ARCH" == "arm64" ]]; then
  if /usr/bin/pgrep oahd >/dev/null 2>&1; then
    log "rosetta2_available=true"
  else
    log "rosetta2_available=false"
    log "Apple Silicon detected but Rosetta 2 service is not running; x86_64 conda may fail."
  fi
  log "creating_conda_env=CONDA_SUBDIR=osx-64 conda create -n $ENV_NAME python=3.11 -y"
  CONDA_SUBDIR=osx-64 conda create -n "$ENV_NAME" python=3.11 -y >> "$DIAG" 2>&1
else
  log "creating_conda_env=conda create -n $ENV_NAME python=3.11 -y"
  conda create -n "$ENV_NAME" python=3.11 -y >> "$DIAG" 2>&1
fi

CREATE_RC=$?
log "conda_create_return_code=$CREATE_RC"
if [[ "$CREATE_RC" -ne 0 ]]; then
  log "Conda environment creation failed. See log above."
  exit 0
fi

ENV_PY="$CONDA_BASE/envs/$ENV_NAME/bin/python"
log "isolated_python=$ENV_PY"

if [[ ! -x "$ENV_PY" ]]; then
  log "isolated_python_exists=false"
  exit 0
fi
log "isolated_python_exists=true"

"$ENV_PY" -m pip install --upgrade pip >> "$DIAG" 2>&1
"$ENV_PY" -m pip install swmm-toolkit pyswmm swmm_api >> "$DIAG" 2>&1
INSTALL_RC=$?
log "pip_install_return_code=$INSTALL_RC"

log "running_isolated_env_test=true"
"$ENV_PY" "$ROOT_DIR/scripts/swmm_env/test_swmm_solver_env.py" >> "$DIAG" 2>&1
TEST_RC=$?
log "test_swmm_solver_env_return_code=$TEST_RC"
log "completed=true"

exit 0

