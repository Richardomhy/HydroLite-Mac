#!/usr/bin/env bash
set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/output/openhydronet_env"
LOG_FILE="$LOG_DIR/clone_repo.log"
REPO_URL="${OPENHYDRONET_REPO_URL:-https://github.com/google-research/flood-forecasting.git}"
TARGET_DIR="${OPENHYDRONET_CLONE_DIR:-$PROJECT_ROOT/external/openhydronet/flood-forecasting}"

mkdir -p "$LOG_DIR"
{
  echo "OpenHydroNet repository clone/update"
  echo "timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "project_root=$PROJECT_ROOT"
  echo "repo_url=$REPO_URL"
  echo "target_dir=$TARGET_DIR"

  if ! grep -qx "external/" "$PROJECT_ROOT/.gitignore"; then
    echo "ERROR: external/ is not ignored by .gitignore"
    exit 1
  fi

  if ! command -v git >/dev/null 2>&1; then
    echo "ERROR: git is not installed or not on PATH"
    exit 1
  fi

  mkdir -p "$(dirname "$TARGET_DIR")"
  if [ -d "$TARGET_DIR/.git" ]; then
    echo "Repository already exists. Running status and git pull --ff-only."
    git -C "$TARGET_DIR" status --short
    git -C "$TARGET_DIR" pull --ff-only
  else
    echo "Cloning repository outside tracked project content."
    git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
  fi

  echo "Final repository status:"
  git -C "$TARGET_DIR" status --short || true
  echo "clone_status=success"
} 2>&1 | tee "$LOG_FILE"

