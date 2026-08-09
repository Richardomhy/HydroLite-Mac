import pandas as pd

from hydrolite.flood_susceptibility_contracts import calculate_class_balance, detect_conflicting_labels, detect_duplicate_points, detect_invalid_coordinates, validate_flood_inventory


def _inventory():
    return pd.DataFrame({"point_id": ["A", "B", "C"], "label": [1, 0, 0], "longitude": [113.0, 113.1, 113.2], "latitude": [22.0, 22.1, 22.2], "inventory_type": ["observed_flood", "pseudo_absence", "verified_non_flood"]})


def test_inventory_qc_detects_duplicates_conflicts_and_invalid_coordinates():
    frame = _inventory()
    assert detect_duplicate_points(pd.concat([frame, frame.iloc[[0]]])).shape[0] == 2
    conflict = pd.concat([frame, frame.iloc[[0]].assign(point_id="D", label=0)])
    assert not detect_conflicting_labels(conflict).empty
    invalid = frame.copy(); invalid.loc[0, "longitude"] = 999
    assert not detect_invalid_coordinates(invalid).empty
    assert validate_flood_inventory(invalid)["status"] == "failed"


def test_pseudo_absence_is_not_verified_and_imbalance_is_reported():
    frame = pd.concat([_inventory(), pd.concat([_inventory().iloc[[1]]] * 10, ignore_index=True)], ignore_index=True)
    result = calculate_class_balance(frame)
    assert result["pseudo_absence_is_verified_non_flood"] is False
    assert result["imbalance_detected"] is True
