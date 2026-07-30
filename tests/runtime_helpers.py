from __future__ import annotations

from pathlib import Path
import json

import yaml


def configure_runtime(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    monkeypatch.setenv("HYDROLITE_RUNTIME_DIR", str(root))
    monkeypatch.setenv("HYDROLITE_RUNTIME_DB", str(root / "hydrolite_runtime.sqlite3"))
    monkeypatch.setenv("HYDROLITE_SETTINGS", str(root / "settings.json"))
    return root


def make_workspace(tmp_path: Path, name: str = "demo") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "project.yaml").write_text(yaml.safe_dump({"project_name": name}), encoding="utf-8")
    (root / "workspace_manifest.json").write_text(json.dumps({"project_name": name, "datasets": []}), encoding="utf-8")
    return root
