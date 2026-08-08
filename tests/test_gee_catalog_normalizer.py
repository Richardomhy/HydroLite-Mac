import json
from pathlib import Path

from hydrolite.gee_catalog.normalizer import normalize_stac_collection


def test_normalizer_handles_collection_and_missing_bands():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "gee_catalog" / "official_stac_minimal.json").read_text())["records"]
    table = normalize_stac_collection(fixture[2])
    assert table["dataset_type"] == "FeatureCollection"
    assert table["bands"] == []
    assert "bands_not_provided" in table["warnings"]
