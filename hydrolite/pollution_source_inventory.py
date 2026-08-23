"""Read-only pollution-source discovery and conservative inventory building."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd

from hydrolite.water_environment_contracts import PollutionSource, PollutionSourceType, SourceInventoryValidationResult
from hydrolite.workspace import calculate_file_checksum


OUTFALL_COLUMNS = {"排污口名称", "经度", "纬度", "排污口分类-一级分类", "排污口分类-二级分类"}


def discover_pollution_source_datasets(source_root: str | Path) -> list[dict[str, Any]]:
    root = Path(source_root).expanduser().resolve()
    if not root.is_dir(): raise FileNotFoundError(f"Source root not found: {root}")
    candidates = sorted({path for path in root.rglob("*.xlsx") if any(token in path.name for token in ("排污口", "污染源", "养殖", "企业"))})
    return [{"dataset_id": "src_" + sha256(str(path.relative_to(root)).encode()).hexdigest()[:12], "logical_path": f"source-root/{path.relative_to(root).as_posix()}", "path": path, "checksum": calculate_file_checksum(path), **classify_source_dataset(path)} for path in candidates]


def classify_source_dataset(path: str | Path) -> dict[str, str]:
    target = Path(path)
    try: columns = set(pd.read_excel(target, nrows=0).columns)
    except Exception as exc: return {"dataset_type": "unknown", "classification_status": "unresolved", "classification_confidence": "low", "message": f"{type(exc).__name__}: {exc}"}
    if OUTFALL_COLUMNS <= columns:
        return {"dataset_type": "pollution_source_inventory", "classification_status": "accepted", "classification_confidence": "high", "message": "Explicit outfall identity, type, and coordinates."}
    return {"dataset_type": "unknown", "classification_status": "manual_confirmation_required", "classification_confidence": "medium", "message": "Filename matched but required source fields were not confirmed."}


def _source_type(subtype: str) -> str:
    return PollutionSourceType.WASTEWATER_TREATMENT.value if "污水处理" in subtype else PollutionSourceType.DIRECT_OUTFALL.value


def build_pollution_source_inventory(dataset: dict[str, Any], project_id: str) -> pd.DataFrame:
    if dataset["classification_status"] != "accepted": raise ValueError("Source dataset requires manual confirmation")
    frame = pd.read_excel(dataset["path"])
    rows = []
    for index, row in frame.iterrows():
        name = "" if pd.isna(row["排污口名称"]) else str(row["排污口名称"]).strip()
        longitude = pd.to_numeric(row["经度"], errors="coerce")
        latitude = pd.to_numeric(row["纬度"], errors="coerce")
        longitude = None if pd.isna(longitude) else float(longitude)
        latitude = None if pd.isna(latitude) else float(latitude)
        grade = "" if pd.isna(row.get("分级")) else str(row.get("分级")).strip()
        subtype = str(row["排污口分类-二级分类"]).strip()
        status = "rejected_not_source" if grade == "非排口" else "manual_confirmation_required" if not grade else "accepted"
        confidence = "high" if status in {"accepted", "rejected_not_source"} else "medium"
        identity = f"{dataset['dataset_id']}:{index + 2}:{name}:{longitude}:{latitude}"
        source_id = "outfall_" + sha256(identity.encode()).hexdigest()[:12]
        source = PollutionSource(
            source_id=source_id, source_type=_source_type(subtype), source_subtype=subtype, name=name,
            project_id=project_id, geometry_type="point", geometry_reference=f"{dataset['dataset_id']}:row:{index + 2}",
            longitude=longitude, latitude=latitude, area=None,
            administrative_unit=str(row.get("详细地址", "")), subbasin_id=None, reach_id=None,
            activity_dataset_id=None, status=status, source_confidence=confidence,
            provenance={"dataset_id": dataset["dataset_id"], "logical_path": dataset["logical_path"], "row": index + 2, "classification_field": "分级"},
            spatial_status="unmapped",
        ).as_dict()
        source.update({
            "drainage_status": row.get("排水特征（排水、无水、有死水、闸断、不确定）"), "field_grade": grade or None,
            "CODMn_concentration_mg_l": pd.to_numeric(row.get("高锰酸钾（mg/L）"), errors="coerce"),
            "NH3-N_concentration_mg_l": pd.to_numeric(row.get("氨氮（mg/L）"), errors="coerce"),
            "TN_concentration_mg_l": pd.to_numeric(row.get("总氮(mg/L)"), errors="coerce"),
            "TP_concentration_mg_l": pd.to_numeric(row.get("总磷（mg/L）"), errors="coerce"),
            "measured_flow_available": False,
        })
        rows.append(source)
    return pd.DataFrame(rows)


def link_sources_to_subbasins(inventory: pd.DataFrame, subbasins_path: str | Path) -> pd.DataFrame:
    result = inventory.copy()
    try:
        import geopandas as gpd
        locatable = result.longitude.notna() & result.latitude.notna()
        geometry = gpd.points_from_xy(result.loc[locatable, "longitude"], result.loc[locatable, "latitude"], crs="EPSG:4326")
        points = gpd.GeoDataFrame(result.loc[locatable, ["source_id"]], geometry=geometry)
        basins = gpd.read_file(subbasins_path)[["subbasin_id", "geometry"]]
        joined = gpd.sjoin(points.to_crs(basins.crs), basins, how="left", predicate="within").set_index("source_id")
        result["subbasin_id"] = result.source_id.map(joined.subbasin_id)
    except Exception:
        result["subbasin_id"] = None
    result["spatial_status"] = result.subbasin_id.notna().map({True: "mapped_low_confidence", False: "unmapped"})
    result["reach_id"] = None
    return result


def link_sources_to_reaches(inventory: pd.DataFrame, reaches_path: str | Path | None = None) -> pd.DataFrame:
    result = inventory.copy()
    result["reach_id"] = None
    return result


def validate_source_inventory(inventory: pd.DataFrame) -> SourceInventoryValidationResult:
    errors, warnings = [], []
    if inventory.source_id.duplicated().any(): errors.append("duplicate_source_id")
    if inventory.source_id.isna().any() or inventory.source_id.astype(str).str.strip().eq("").any(): errors.append("missing_source_id")
    if inventory.name.isna().any() or inventory.name.astype(str).str.strip().eq("").any(): warnings.append("source_name_missing")
    if (~inventory.source_type.isin({item.value for item in PollutionSourceType})).any(): errors.append("unknown_source_type")
    accepted = inventory.status.eq("accepted")
    if inventory.loc[accepted, ["longitude", "latitude"]].isna().any(axis=None): warnings.append("accepted_source_coordinates_missing")
    return SourceInventoryValidationResult("passed" if not errors else "failed", len(inventory), int(accepted.sum()), int(inventory.status.eq("manual_confirmation_required").sum()), tuple(errors), tuple(warnings))


def summarize_source_inventory(inventory: pd.DataFrame) -> dict[str, Any]:
    considered = inventory.status.isin(["accepted", "manual_confirmation_required"])
    return {
        "sources_discovered": len(inventory), "sources_accepted": int(inventory.status.eq("accepted").sum()),
        "sources_unresolved": int(inventory.status.eq("manual_confirmation_required").sum()),
        "sources_rejected_not_source": int(inventory.status.eq("rejected_not_source").sum()),
        "spatial_mapped": int((considered & inventory.spatial_status.eq("mapped_low_confidence")).sum()),
        "spatial_unresolved": int((considered & inventory.spatial_status.eq("unmapped")).sum()),
        "source_counts_by_type": inventory.loc[considered, "source_type"].value_counts().to_dict(),
        "confidence_distribution": inventory.loc[considered, "source_confidence"].value_counts().to_dict(),
    }


def write_source_inventory_geojson(inventory: pd.DataFrame, path: str | Path) -> Path:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for row in inventory.loc[inventory.status.isin(["accepted", "manual_confirmation_required"])].itertuples(index=False):
        properties = {key: value for key, value in row._asdict().items() if key not in {"longitude", "latitude", "provenance"} and pd.notna(value)}
        geometry = None if pd.isna(row.longitude) or pd.isna(row.latitude) else {"type": "Point", "coordinates": [row.longitude, row.latitude]}
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    target.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, default=str), encoding="utf-8")
    return target
