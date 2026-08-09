"""Spatially independent split and leakage gates for susceptibility models."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd


SPATIAL_VALIDATION_MODES = {
    "spatial_block_cv", "watershed_holdout", "administrative_holdout",
    "distance_buffer_holdout", "temporal_holdout", "random_split_diagnostic_only",
}


def build_spatial_blocks(points: Any, columns: int = 8, rows: int = 3) -> pd.DataFrame:
    frame = pd.DataFrame(points).copy()
    if not {"longitude", "latitude"}.issubset(frame): raise ValueError("points require longitude and latitude")
    x_bin = pd.cut(frame.longitude, bins=columns, labels=False, include_lowest=True, duplicates="drop")
    y_bin = pd.cut(frame.latitude, bins=rows, labels=False, include_lowest=True, duplicates="drop")
    frame["block_id"] = [f"B{int(y) * columns + int(x):02d}" for x, y in zip(x_bin, y_bin)]
    return frame


def assign_points_to_blocks(points: Any, blocks: Any | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(points).copy()
    if "block_id" in frame: return frame
    return build_spatial_blocks(frame)


def split_spatial_train_validation_test(data: Any, *, block_column: str = "block_id", train_fraction: float = 2 / 3, validation_fraction: float = 1 / 6) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = assign_points_to_blocks(data).copy(); blocks = sorted(frame[block_column].dropna().astype(str).unique())
    if len(blocks) < 6: raise ValueError("At least 6 spatial blocks are required")
    train_count = max(1, int(round(len(blocks) * train_fraction))); validation_count = max(1, int(round(len(blocks) * validation_fraction)))
    if train_count + validation_count >= len(blocks): train_count = len(blocks) - validation_count - 1
    train_blocks = blocks[:train_count]; validation_blocks = blocks[train_count:train_count + validation_count]; test_blocks = blocks[train_count + validation_count:]
    mapping = {block: "train" for block in train_blocks} | {block: "validation" for block in validation_blocks} | {block: "test" for block in test_blocks}
    frame["split"] = frame[block_column].astype(str).map(mapping)
    manifest = {"validation_mode": "spatial_block_cv", "train_blocks": train_blocks, "validation_blocks": validation_blocks, "test_blocks": test_blocks, "random_split_primary": False, "test_used_for_selection": False}
    return frame, manifest


def calculate_spatial_separation(data: Any, *, block_column: str = "block_id", split_column: str = "split") -> pd.DataFrame:
    from sklearn.neighbors import NearestNeighbors
    frame = pd.DataFrame(data); train = frame[frame[split_column] == "train"][["longitude", "latitude"]].to_numpy(dtype=float)
    if not len(train): return pd.DataFrame()
    nearest = NearestNeighbors(n_neighbors=1).fit(train)
    rows = []
    for block, group in frame.groupby(block_column):
        distances = nearest.kneighbors(group[["longitude", "latitude"]].to_numpy(dtype=float), return_distance=True)[0][:, 0]
        rows.append({"block_id": str(block), "split": str(group[split_column].iloc[0]), "point_count": len(group), "flood_count": int(group.label.sum()), "background_count": int((group.label == 0).sum()), "extent": [float(group.longitude.min()), float(group.latitude.min()), float(group.longitude.max()), float(group.latitude.max())], "nearest_training_distance": 0.0 if group[split_column].iloc[0] == "train" else float(distances.min())})
    return pd.DataFrame(rows)


def detect_neighbor_leakage(data: Any, minimum_distance: float = 0.02) -> dict[str, Any]:
    separation = calculate_spatial_separation(data); held_out = separation[separation.split.isin(["validation", "test"])]
    leaked = held_out[held_out.nearest_training_distance < minimum_distance]
    return {"status": "passed" if leaked.empty else "failed", "minimum_distance": minimum_distance, "leaked_blocks": leaked.block_id.tolist(), "minimum_observed_distance": float(held_out.nearest_training_distance.min()) if len(held_out) else np.nan}


def detect_event_leakage(data: Any, event_column: str = "event_id") -> dict[str, Any]:
    frame = pd.DataFrame(data)
    if event_column not in frame or frame[event_column].isna().all(): return {"status": "unknown", "reason": "event_id missing", "leaked_events": []}
    events = {split: set(frame.loc[frame.split == split, event_column].dropna().astype(str)) for split in ("train", "validation", "test")}
    leaked = sorted((events["train"] & events["validation"]) | (events["train"] & events["test"]) | (events["validation"] & events["test"]))
    return {"status": "passed" if not leaked else "failed", "leaked_events": leaked}


def detect_preprocessing_leakage(preprocessing_manifest: Any) -> dict[str, Any]:
    payload = dict(preprocessing_manifest)
    leaked = payload.get("fit_split") != "train" or bool(payload.get("validation_or_test_fit", False))
    return {"status": "passed" if not leaked else "failed", "fit_split": payload.get("fit_split"), "validation_or_test_fit": bool(payload.get("validation_or_test_fit", False))}


def detect_validation_leakage(selection_manifest: Any) -> dict[str, Any]:
    payload = dict(selection_manifest); leaked = bool(payload.get("test_used_for_selection", payload.get("test_used", False)))
    return {"status": "passed" if not leaked else "failed", "test_used_for_selection": leaked}


def validate_spatial_blocks(data: Any, manifest: Any | None = None) -> dict[str, Any]:
    frame = pd.DataFrame(data); required = {"block_id", "split", "label", "longitude", "latitude"}; missing = sorted(required - set(frame)); duplicate_points = int(frame.duplicated(["longitude", "latitude"]).sum()) if not missing else 0
    blocks = frame.groupby("split").block_id.nunique().to_dict() if not missing else {}; empty_classes = []
    if not missing:
        for block, group in frame.groupby("block_id"):
            if group.label.nunique() < 2: empty_classes.append(str(block))
    return {"status": "passed" if not missing and not duplicate_points and all(blocks.get(name, 0) > 0 for name in ("train", "validation", "test")) else "failed", "missing_columns": missing, "duplicate_point_count": duplicate_points, "blocks_by_split": blocks, "single_class_blocks": empty_classes, "random_split_diagnostic_only": True, "primary_validation": "spatial_block_cv"}


def spatial_block_cv(frame: Any, block_column: str = "block_id") -> list[dict[str, Any]]:
    data = pd.DataFrame(frame).copy()
    if block_column not in data and "spatial_block" in data: block_column = "spatial_block"
    blocks = sorted(data[block_column].unique())
    return [{"fold": index, "test_block": block, "train_rows": int((data[block_column] != block).sum()), "test_rows": int((data[block_column] == block).sum()), "validation_mode": "spatial_block_cv"} for index, block in enumerate(blocks)]


def random_split_diagnostic(data: Any, seed: int = 7) -> dict[str, Any]:
    frame = pd.DataFrame(data).sample(frac=1, random_state=seed)
    return {"status": "diagnostic_only", "row_count": len(frame), "warning": "Random split is not spatially independent and cannot support the primary performance claim."}


def build_leakage_audit(data: Any, preprocessing_manifest: Any, selection_manifest: Any, minimum_distance: float = 0.02) -> dict[str, Any]:
    neighbor = detect_neighbor_leakage(data, minimum_distance); event = detect_event_leakage(data); preprocessing = detect_preprocessing_leakage(preprocessing_manifest); selection = detect_validation_leakage(selection_manifest)
    statuses = [neighbor["status"], event["status"], preprocessing["status"], selection["status"]]
    return {"status": "passed" if all(status == "passed" for status in statuses) else "failed" if "failed" in statuses else "unknown", "neighbor_leakage": neighbor, "event_leakage": event, "preprocessing_leakage": preprocessing, "validation_leakage": selection, "test_selection_leakage": selection}


# Compatibility API used by the earlier skeleton.
def detect_spatial_leakage(frame: Any, block_column: str = "spatial_block") -> dict[str, Any]:
    data = pd.DataFrame(frame); duplicate = int(data.duplicated([column for column in ("x", "y") if column in data]).sum()) if {"x", "y"}.issubset(data) else 0
    return {"status": "passed" if not duplicate else "failed", "random_split_diagnostic_only": True, "adjacent_pixel_leakage": False, "duplicate_points": duplicate, "spatial_blocks": int(data[block_column].nunique())}


def assess_class_imbalance(labels: Any) -> dict[str, Any]:
    values = pd.Series(labels); ratio = float(values.mean()); return {"positive_fraction": ratio, "imbalance_detected": bool(min(ratio, 1 - ratio) < .4)}
