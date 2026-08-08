from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Iterator

import pandas as pd

from hydrolite.gee_catalog.paths import CatalogPaths, get_catalog_paths
from hydrolite.gee_catalog.normalizer import normalize_record


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data_demo" / "method_inspiration" / "gee_catalog" / "official_metadata_fixture.json"


def load_test_fixture(path: str | Path = FIXTURE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fixture_records() -> list[dict]:
    return [normalize_record(row) for row in load_test_fixture().get("records", [])]


def load_catalog_manifest(path: str | Path | None = None) -> dict:
    paths = get_catalog_paths(path) if path else get_catalog_paths()
    if paths.manifest.exists(): return json.loads(paths.manifest.read_text(encoding="utf-8"))
    return {"status": "fixture_only", "source": "repository test fixture", "record_count": len(fixture_records())}


def iterate_catalog_records(path: str | Path | None = None) -> Iterator[dict]:
    paths = get_catalog_paths(path) if path else get_catalog_paths()
    if paths.records.exists():
        with gzip.open(paths.records, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip(): yield json.loads(line)
        return
    yield from fixture_records()


def load_catalog_records(path: str | Path | None = None) -> list[dict]:
    return list(iterate_catalog_records(path))


def load_catalog(path: str | Path | None = None) -> list[dict]:
    return load_catalog_records(path)


def load_catalog_index(path: str | Path | None = None) -> pd.DataFrame:
    paths = get_catalog_paths(path) if path else get_catalog_paths()
    if paths.index.exists(): return pd.read_parquet(paths.index)
    return pd.DataFrame(load_catalog_records(paths.root))


def get_catalog_dataset(asset_id: str, path: str | Path | None = None) -> dict | None:
    wanted = asset_id.lower()
    return next((row for row in iterate_catalog_records(path) if str(row.get("asset_id", "")).lower() == wanted), None)


def inspect_catalog_availability(path: str | Path | None = None) -> dict:
    paths = get_catalog_paths(path) if path else get_catalog_paths()
    has_local = paths.records.exists() and paths.manifest.exists()
    manifest = load_catalog_manifest(paths.root)
    return {"status": manifest.get("catalog_completeness", "available") if has_local else "fixture_only", "catalog_completeness": manifest.get("catalog_completeness", "fixture_only"), "catalog_root": str(paths.root), "records_path": str(paths.records), "manifest_path": str(paths.manifest), "fixture_path": str(FIXTURE), "record_count": len(load_catalog_records(paths.root)), "local_catalog": has_local}
