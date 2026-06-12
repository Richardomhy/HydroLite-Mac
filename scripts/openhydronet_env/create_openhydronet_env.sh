#!/usr/bin/env bash
set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/output/openhydronet_env"
LOG_FILE="$LOG_DIR/create_env.log"
ENV_NAME="${OPENHYDRONET_ENV_NAME:-hydrolite-openhydronet}"
REPO_DIR="${OPENHYDRONET_HOME:-$PROJECT_ROOT/external/openhydronet/flood-forecasting}"

mkdir -p "$LOG_DIR"
{
  echo "OpenHydroNet isolated environment setup"
  echo "timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "project_root=$PROJECT_ROOT"
  echo "env_name=$ENV_NAME"
  echo "repo_dir=$REPO_DIR"
  echo "macos=$(sw_vers -productVersion 2>/dev/null || echo unknown)"
  echo "machine=$(uname -m)"
  echo "shell_arch=$(arch 2>/dev/null || echo unknown)"

  if ! command -v conda >/dev/null 2>&1; then
    echo "env_status=unavailable"
    echo "error=conda is not installed or not on PATH"
    exit 0
  fi

  CONDA_BASE="$(conda info --base 2>/dev/null || true)"
  echo "conda_base=$CONDA_BASE"
  if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "env_status=exists"
  else
    echo "Creating conda environment with python=3.11"
    if conda create -n "$ENV_NAME" python=3.11 -y; then
      echo "python_version_selected=3.11"
    else
      echo "python=3.11 failed; retrying python=3.10"
      conda create -n "$ENV_NAME" python=3.10 -y
      echo "python_version_selected=3.10"
    fi
  fi

  echo "Installing base dependencies in isolated environment"
  conda run -n "$ENV_NAME" python -m pip install --upgrade pip
  conda run -n "$ENV_NAME" python -m pip install torch numpy pandas pyyaml openpyxl

  if [ -f "$REPO_DIR/requirements.txt" ]; then
    echo "Installing external repository requirements: $REPO_DIR/requirements.txt"
    conda run -n "$ENV_NAME" python -m pip install -r "$REPO_DIR/requirements.txt" || echo "requirements_install_status=failed"
  else
    echo "requirements_install_status=skipped_no_requirements_file"
  fi

  ENV_PY="$CONDA_BASE/envs/$ENV_NAME/bin/python"
  echo "env_status=ready"
  echo "env_python=$ENV_PY"
  "$ENV_PY" --version || true
} 2>&1 | tee "$LOG_FILE"

