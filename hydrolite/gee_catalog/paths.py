from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class CatalogPaths:
    root: Path

    @property
    def records(self) -> Path: return self.root / "catalog.jsonl.gz"
    @property
    def index(self) -> Path: return self.root / "catalog_index.parquet"
    @property
    def manifest(self) -> Path: return self.root / "manifest.json"
    @property
    def validation(self) -> Path: return self.root / "validation.json"
    @property
    def history(self) -> Path: return self.root / "refresh_history.jsonl"
    @property
    def statistics(self) -> Path: return self.root / "catalog_statistics.json"
    @property
    def backups(self) -> Path: return self.root / "backups"
    @property
    def staging(self) -> Path: return self.root / "staging"


def get_catalog_paths(root: str | Path | None = None) -> CatalogPaths:
    if root:
        return CatalogPaths(Path(root).expanduser().resolve())
    if os.getenv("HYDROLITE_DESKTOP") == "1":
        base = Path.home() / "Library" / "Application Support" / "HydroLite Studio" / "catalogs" / "gee"
    else:
        base = Path.home() / ".hydrolite" / "catalogs" / "gee"
    return CatalogPaths(base)
