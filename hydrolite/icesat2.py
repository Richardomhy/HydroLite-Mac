"""Local-first, constrained ICESat-2 water-depth MVP."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data_demo" / "icesat2"
DEFAULT_OUTPUT = ROOT / "output" / "icesat2"
COLUMNS = ["product", "product_version", "granule_id", "acquisition_time", "beam", "latitude", "longitude", "along_track_distance_m", "water_surface_height_m", "bottom_height_m", "apparent_depth_m", "corrected_depth_m", "vertical_reference", "depth_uncertainty_m", "signal_confidence", "quality_flag", "source_group", "processing_status", "warnings"]

def _path(value: str | Path) -> Path: return Path(value).expanduser().resolve()
def _empty() -> pd.DataFrame: return pd.DataFrame(columns=COLUMNS)

def detect_icesat2_dependencies() -> dict[str, Any]:
    names = ("h5py", "numpy", "pandas", "geopandas", "shapely", "earthaccess", "pyproj")
    found = {name: importlib.util.find_spec(name) is not None for name in names}
    try:
        from hydrolite.qgis_bridge import get_qgis_process_path
        qgis = str(get_qgis_process_path() or "")
    except Exception: qgis = ""
    return {"status": "available", "dependencies": found, "qgis_process": qgis, "optional_unavailable": [k for k, v in found.items() if not v and k not in {"numpy", "pandas"}]}

def detect_earthdata_access() -> dict[str, Any]:
    authenticated = bool(os.getenv("EARTHDATA_TOKEN") or (os.getenv("EARTHDATA_USERNAME") and os.getenv("EARTHDATA_PASSWORD")))
    return {"authenticated": authenticated, "status": "authenticated" if authenticated else "authentication_required", "earthaccess_available": importlib.util.find_spec("earthaccess") is not None}

def identify_icesat2_product(file_path: str | Path) -> dict[str, Any]:
    path = _path(file_path); name = path.name.upper()
    product = next((item for item in ("ATL13", "ATL24", "ATL03") if item in name), None)
    if path.suffix.lower() == ".csv" and not product:
        try: product = str(pd.read_csv(path, nrows=1).get("product", ["ATL13"])[0]).upper()
        except Exception: product = "unknown"
    return {"path": str(path), "exists": path.exists(), "product": product or "unknown", "file_type": path.suffix.lower()}

def inspect_icesat2_hdf5(file_path: str | Path) -> dict[str, Any]:
    info = identify_icesat2_product(file_path)
    if not info["exists"]: return {**info, "status": "missing_file"}
    if _path(file_path).suffix.lower() not in {".h5", ".hdf5"}: return {**info, "status": "not_hdf5"}
    if importlib.util.find_spec("h5py") is None: return {**info, "status": "optional_unavailable"}
    import h5py
    with h5py.File(_path(file_path), "r") as handle: groups = list(handle.keys())
    return {**info, "status": "inspected", "groups": groups}

def select_icesat2_product_for_waterbody(waterbody_type: str, purpose: str) -> dict[str, Any]:
    inland = waterbody_type.lower() in {"inland_reservoir", "inland_lake", "inland_river", "reservoir", "lake", "river"}
    coastal = waterbody_type.lower() in {"coastal", "nearshore", "estuary", "river_mouth"}
    return {"recommended_product": "ATL13" if inland or not coastal else "ATL24", "secondary_product": "ATL03" if inland or not coastal else "ATL13", "waterbody_type": waterbody_type, "purpose": purpose, "suitability": "preferred" if inland or coastal else "review_required", "limitations": ["ICESat-2 is along-track; bottom signal is not guaranteed."], "warnings": ["ATL24 is incompatible_product for ordinary inland water bodies."] if inland else []}

def search_icesat2_granules(bbox: str | list[float], start_date: str, end_date: str, products: list[str] | None = None, max_granules: int = 20) -> dict[str, Any]:
    if not bbox or not start_date or not end_date: raise ValueError("ICESat-2 search requires bbox, start_date and end_date.")
    if not 1 <= max_granules <= 20: raise ValueError("max_granules must be 1-20.")
    return {"status": "authentication_required" if not detect_earthdata_access()["authenticated"] else "query_not_executed", "bbox": bbox, "start_date": start_date, "end_date": end_date, "products": products or ["ATL13"], "max_granules": max_granules, "granules": []}

def download_icesat2_granules(search_result: dict[str, Any], output_dir: str | Path, execute: bool = False) -> dict[str, Any]:
    root = _path(output_dir); root.mkdir(parents=True, exist_ok=True)
    return {"status": "dry_run" if not execute else "not_implemented", "downloaded": [], "output_dir": str(root)}

def _load(file_path: str | Path, product: str) -> pd.DataFrame:
    path = _path(file_path)
    if path.suffix.lower() != ".csv":
        return _empty().assign(processing_status="optional_unavailable", warnings="HDF5 layout extraction requires optional h5py/product mapping.")
    data = pd.read_csv(path)
    for column in COLUMNS:
        if column not in data: data[column] = np.nan
    data["product"] = data["product"].fillna(product).astype(str).str.upper()
    data["warnings"] = data["warnings"].fillna("synthetic_demo only")
    data["processing_status"] = data["processing_status"].fillna("synthetic_demo_extracted")
    return data[COLUMNS]

def extract_atl13_water_data(file_path: str | Path, waterbody_geometry: str | Path | None = None) -> pd.DataFrame: return _load(file_path, "ATL13")
def extract_atl24_bathymetry(file_path: str | Path, waterbody_geometry: str | Path | None = None) -> pd.DataFrame: return _load(file_path, "ATL24")
def extract_atl03_photons(file_path: str | Path, waterbody_geometry: str | Path | None = None) -> pd.DataFrame: return _load(file_path, "ATL03").assign(processing_status="experimental_raw_photon_source")
def classify_atl03_water_photons_experimental(data: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame: return data.copy().assign(processing_status="experimental")

def filter_icesat2_quality(data: pd.DataFrame, product: str) -> pd.DataFrame:
    out = data.copy(); s = pd.to_numeric(out["water_surface_height_m"], errors="coerce"); b = pd.to_numeric(out["bottom_height_m"], errors="coerce"); c = pd.to_numeric(out["signal_confidence"], errors="coerce").fillna(0)
    xy = pd.to_numeric(out["latitude"], errors="coerce").between(-90, 90) & pd.to_numeric(out["longitude"], errors="coerce").between(-180, 180)
    valid = xy & s.notna() & b.notna() & (s > b)
    out["quality_class"] = np.select([valid & (c >= .8), valid & (c >= .5), valid, xy & b.isna()], ["accepted_high", "accepted_medium", "accepted_low", "surface_only"], default="rejected")
    return out.drop_duplicates(subset=["granule_id", "beam", "along_track_distance_m"])

def validate_vertical_reference(data: pd.DataFrame) -> dict[str, Any]:
    refs = sorted(set(data["vertical_reference"].dropna().astype(str).str.lower()))
    status = "consistent" if len(refs) == 1 and refs[0] in {"wgs84 ellipsoidal", "ellipsoidal", "orthometric"} else "datum_mismatch" if len(refs) > 1 else "unknown"
    return {"status": status, "references": refs, "can_compute_storage": status == "consistent"}

def normalize_vertical_reference(data: pd.DataFrame, target_reference: str | None = None) -> pd.DataFrame:
    if validate_vertical_reference(data)["status"] == "datum_mismatch" and target_reference is None: raise ValueError("datum_mismatch: reliable conversion required.")
    return data.copy().assign(normalized_vertical_reference=target_reference or validate_vertical_reference(data)["references"][0])

def estimate_icesat2_water_depth(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy(); apparent = pd.to_numeric(out["water_surface_height_m"], errors="coerce") - pd.to_numeric(out["bottom_height_m"], errors="coerce")
    provided = pd.to_numeric(out["corrected_depth_m"], errors="coerce"); out["apparent_depth_m"] = apparent
    out["corrected_depth_m"] = provided.where(provided.notna(), apparent).where(lambda x: x > 0)
    out["method_status"] = np.where(out["product"].eq("ATL03"), "experimental", "product_depth_or_constraint")
    return out

def build_icesat2_depth_profiles(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (granule, beam), frame in data[data["quality_class"].isin(["accepted_high", "accepted_medium"])].groupby(["granule_id", "beam"]):
        d = pd.to_numeric(frame["corrected_depth_m"], errors="coerce").dropna(); x = pd.to_numeric(frame["along_track_distance_m"], errors="coerce").sort_values()
        rows.append({"profile_id": f"{granule}_{beam}", "granule_id": granule, "beam": beam, "length_m": float(x.max()-x.min()), "accepted_points": len(frame), "surface_only_points": int(((data["granule_id"]==granule)&(data["beam"]==beam)&(data["quality_class"]=="surface_only")).sum()), "median_depth_m": float(d.median()), "maximum_depth_m": float(d.max()), "depth_p05_m": float(d.quantile(.05)), "depth_p50_m": float(d.quantile(.5)), "depth_p95_m": float(d.quantile(.95)), "median_uncertainty_m": float(pd.to_numeric(frame["depth_uncertainty_m"], errors="coerce").median()), "maximum_gap_m": float(x.diff().max() or 0), "coverage_status": "adequate_for_profile" if len(frame)>=3 else "limited", "warnings": "along-track only"})
    return pd.DataFrame(rows)

def _area(geometry: str | Path) -> float:
    data = json.loads(_path(geometry).read_text()); feature = data.get("features", [data])[0]
    return float((feature.get("properties") or {}).get("area_m2", 0))

def calculate_icesat2_track_coverage(data: pd.DataFrame, waterbody_geometry: str | Path) -> dict[str, Any]:
    accepted = data[data["quality_class"].isin(["accepted_high", "accepted_medium"])]
    tracks = accepted[["granule_id", "beam"]].drop_duplicates()
    return {"waterbody_area_m2": _area(waterbody_geometry), "track_count": len(tracks), "total_track_length_m": float(accepted.groupby(["granule_id","beam"])["along_track_distance_m"].agg(lambda x: pd.to_numeric(x).max()-pd.to_numeric(x).min()).sum()), "valid_depth_length_m": float(accepted.groupby(["granule_id","beam"])["along_track_distance_m"].agg(lambda x: pd.to_numeric(x).max()-pd.to_numeric(x).min()).sum()), "max_track_spacing_m": None, "valid_depth_points": len(accepted), "coverage_ratio_definition": "along-track diagnostic, not area coverage", "spatial_coverage_status": "adequate_for_profile" if len(tracks)>=2 and len(accepted)>=6 else "limited" if len(accepted) else "no_bottom_signal"}

def interpolate_depth_surface_limited(depth_points: pd.DataFrame, waterbody_geometry: str | Path, max_distance_m: float | None = None) -> dict[str, Any]:
    coverage = calculate_icesat2_track_coverage(depth_points, waterbody_geometry)
    return {"status": "insufficient_spatial_coverage", "surface": None, "warnings": ["No continuous depth surface generated; only constrained profiles are valid."]} if coverage["track_count"] < 2 else {"status": "limited_interpolation_not_written", "surface": None, "max_distance_m": max_distance_m}
def build_waterbody_depth_constraint(depth_points: pd.DataFrame, waterbody_geometry: str | Path, dem_path: str | Path | None = None) -> dict[str, Any]: return interpolate_depth_surface_limited(depth_points, waterbody_geometry)

def build_stage_area_volume_curve(waterbody_geometry: str | Path, dem_path: str | Path | None, water_level_range: list[float] | None = None, depth_constraints: pd.DataFrame | None = None) -> pd.DataFrame:
    area = _area(waterbody_geometry)
    if area <= 0: raise ValueError("Verified projected area_m2 is required; degrees cannot calculate storage.")
    stage = float(pd.to_numeric(depth_constraints["water_surface_height_m"], errors="coerce").median()) if depth_constraints is not None else 100.
    levels = water_level_range or [stage-1, stage, stage+1]; base = min(levels)
    return pd.DataFrame({"stage_m": levels, "area_m2": area, "volume_m3": [area*(level-base) for level in levels], "status": "constraint_only"})
def validate_stage_storage_curve(curve: pd.DataFrame) -> dict[str, Any]: return {"status": "passed" if not curve.empty and curve["volume_m3"].is_monotonic_increasing else "failed", "records": len(curve)}
def export_stage_storage_for_hydrolite(curve: pd.DataFrame, output_csv: str | Path) -> Path: p=_path(output_csv);p.parent.mkdir(parents=True,exist_ok=True);curve.to_csv(p,index=False);return p
def export_stage_storage_for_hec_hms(curve: pd.DataFrame, output_csv: str | Path) -> Path: return export_stage_storage_for_hydrolite(curve.rename(columns={"stage_m":"elevation_m","volume_m3":"storage_m3"}),output_csv)
def validate_icesat2_depth_result(result: dict[str, Any]) -> dict[str, Any]: return {"status": "passed" if result["vertical_reference"]["status"]=="consistent" else "partial", "vertical_reference_status": result["vertical_reference"]["status"], "coverage_status": result["coverage"]["spatial_coverage_status"]}

def write_icesat2_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    root=_path(output_dir);root.mkdir(parents=True,exist_ok=True);points=result["points"];points.to_csv(root/"water_surface_points.csv",index=False);points[points["quality_class"].isin(["accepted_high","accepted_medium","accepted_low"])].to_csv(root/"bathymetry_points.csv",index=False);result["profiles"].to_csv(root/"depth_profiles.csv",index=False);result["curve"].to_csv(root/"stage_area_volume.csv",index=False)
    with pd.ExcelWriter(root/"track_coverage.xlsx") as w: pd.DataFrame([result["coverage"]]).to_excel(w,index=False)
    with pd.ExcelWriter(root/"depth_quality_summary.xlsx") as w: points.groupby("quality_class").size().reset_index(name="point_count").to_excel(w,index=False)
    charts=root/"charts";charts.mkdir(exist_ok=True)
    for name,col in [("depth_profile.png","corrected_depth_m"),("depth_uncertainty.png","depth_uncertainty_m")]:
        fig,ax=plt.subplots();ax.plot(points["along_track_distance_m"],points[col],marker="o");ax.set(xlabel="along-track m",ylabel=col);fig.tight_layout();fig.savefig(charts/name,dpi=120);plt.close(fig)
    (root/"product_selection.json").write_text(json.dumps(result["product_selection"],indent=2)+"\n");(root/"icesat2_diagnosis.json").write_text(json.dumps({"dependencies":detect_icesat2_dependencies(),"earthdata":detect_earthdata_access(),"validation":result["validation"]},indent=2)+"\n");(root/"icesat2_diagnosis.md").write_text("# ICESat-2 diagnosis\n\nLocal-first constrained MVP.\n");report=root/"icesat2_water_depth_report.md";report.write_text("# ICESat-2 Water Depth Constraint Report\n\nSynthetic demo only. ICESat-2 provides water surface elevation, along-track water depth estimate, shallow bathymetry constraint and stage-storage constraint; not complete bathymetry.\n");(root/"icesat2_manifest.json").write_text(json.dumps({"synthetic_demo":True,"generated_at":datetime.now(timezone.utc).isoformat(),"validation":result["validation"]},indent=2)+"\n");return report

def run_icesat2_demo(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    selection=select_icesat2_product_for_waterbody("inland_reservoir","depth");points=estimate_icesat2_water_depth(filter_icesat2_quality(extract_atl13_water_data(DEMO/"demo_atl13_extract.csv"),"ATL13"));profiles=build_icesat2_depth_profiles(points);vertical=validate_vertical_reference(points);coverage=calculate_icesat2_track_coverage(points,DEMO/"demo_waterbody.geojson");curve=build_stage_area_volume_curve(DEMO/"demo_waterbody.geojson",None,depth_constraints=points);result={"product_selection":selection,"points":points,"profiles":profiles,"vertical_reference":vertical,"coverage":coverage,"curve":curve};result["validation"]=validate_icesat2_depth_result(result);result["report"]=write_icesat2_report(output_dir,result);return result
def validate_icesat2_outputs(output_dir: str | Path) -> dict[str, Any]:
    root=_path(output_dir);required=["icesat2_diagnosis.json","water_surface_points.csv","bathymetry_points.csv","depth_profiles.csv","track_coverage.xlsx","depth_quality_summary.xlsx","stage_area_volume.csv","icesat2_water_depth_report.md","icesat2_manifest.json"];missing=[x for x in required if not (root/x).exists()];return {"status":"passed" if not missing else "failed","missing":missing}
