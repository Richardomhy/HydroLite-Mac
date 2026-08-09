from hydrolite.flood_susceptibility_features import build_synthetic_flood_features
from hydrolite.flood_susceptibility_validation import assess_class_imbalance, detect_spatial_leakage, spatial_block_cv
from hydrolite.spatial_validation import random_split_diagnostic, split_spatial_train_validation_test, validate_spatial_blocks


def test_spatial_blocks_and_imbalance_diagnostics():
    frame=build_synthetic_flood_features(); assert len(spatial_block_cv(frame))==6 and assess_class_imbalance(frame.flood)["imbalance_detected"] and not detect_spatial_leakage(frame)["adjacent_pixel_leakage"]


def test_primary_split_has_independent_spatial_blocks_and_random_is_diagnostic_only():
    frame = build_synthetic_flood_features(120).rename(columns={"x": "longitude", "y": "latitude", "flood": "label", "spatial_block": "block_id"})
    frame["event_id"] = [f"E{block}_{index}" for index, block in enumerate(frame.block_id)]
    split, manifest = split_spatial_train_validation_test(frame)
    assert validate_spatial_blocks(split, manifest)["status"] == "passed"
    assert set(split.loc[split.split == "train", "block_id"]).isdisjoint(set(split.loc[split.split == "test", "block_id"]))
    assert random_split_diagnostic(frame)["status"] == "diagnostic_only"
