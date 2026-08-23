from __future__ import annotations

import json

import pandas as pd

from hydrolite.pollution_source_inventory import (
    build_pollution_source_inventory, classify_source_dataset,
    discover_pollution_source_datasets, summarize_source_inventory,
    validate_source_inventory, write_source_inventory_geojson,
)


def _write_inventory(path):
    pd.DataFrame([
        {"排污口名称": "A", "经度": 113.9, "纬度": 22.5, "排污口分类-一级分类": "其他排污口", "排污口分类-二级分类": "农村污水处理设施排口", "分级": "一级"},
        {"排污口名称": "B", "经度": 113.91, "纬度": 22.51, "排污口分类-一级分类": "其他排污口", "排污口分类-二级分类": "其他", "分级": None},
        {"排污口名称": "C", "经度": 113.92, "纬度": 22.52, "排污口分类-一级分类": "其他排污口", "排污口分类-二级分类": "其他", "分级": "非排口"},
    ]).to_excel(path, index=False)


def test_inventory_discovery_classification_and_conservative_status(tmp_path):
    path = tmp_path / "匿名排污口.xlsx"; _write_inventory(path)
    assert classify_source_dataset(path)["classification_confidence"] == "high"
    datasets = discover_pollution_source_datasets(tmp_path)
    assert len(datasets) == 1 and datasets[0]["classification_status"] == "accepted"
    inventory = build_pollution_source_inventory(datasets[0], "anonymous_project")
    assert inventory.source_id.is_unique
    assert inventory.status.tolist() == ["accepted", "manual_confirmation_required", "rejected_not_source"]
    assert inventory.source_type.tolist()[0] == "wastewater_treatment"
    assert not inventory.measured_flow_available.any()
    validation = validate_source_inventory(inventory)
    assert validation.status == "passed"
    assert summarize_source_inventory(inventory)["sources_unresolved"] == 1


def test_geojson_does_not_invent_missing_coordinates(tmp_path):
    path = tmp_path / "匿名排污口.xlsx"; _write_inventory(path)
    dataset = discover_pollution_source_datasets(tmp_path)[0]
    inventory = build_pollution_source_inventory(dataset, "anonymous_project")
    inventory.loc[0, ["longitude", "latitude"]] = None
    target = write_source_inventory_geojson(inventory, tmp_path / "inventory.geojson")
    features = json.loads(target.read_text(encoding="utf-8"))["features"]
    assert features[0]["geometry"] is None
