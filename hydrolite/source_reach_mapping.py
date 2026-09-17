"""Geometric candidates remain distinct from reviewed computational reach IDs."""

import json
import re

import pandas as pd


def normalized_water_name(value: str, aliases: dict[str, str] | None = None) -> str:
    text = re.sub(r"[\s（）()]+", "", str(value))
    return (aliases or {}).get(text, text)


def map_source_reaches(sources, subbasins, reaches, *, source_crs=None, coordinate_evidence="", analysis_crs=None, aliases=None, near_distance_m=100.0):
    import geopandas as gpd
    from pyproj import CRS
    from shapely.geometry import Point
    if not subbasins.crs or not reaches.crs: raise ValueError("Spatial layer CRS required")
    crs = CRS.from_user_input(analysis_crs or subbasins.crs)
    if not crs.is_projected or crs.axis_info[0].unit_name != "metre": raise ValueError("Metric analysis CRS required")
    basins = subbasins.to_crs(crs); lines = reaches.to_crs(crs)
    if basins.geometry.isna().any() or not basins.geometry.is_valid.all() or lines.geometry.isna().any() or not lines.geometry.is_valid.all(): raise ValueError("Invalid reference geometry")
    rows = []
    for source in sources.to_dict("records"):
        row = {"source_id": source["source_id"], "subbasin_id": None, "reach_id": None, "candidate_river_line": None, "mapping_method": "unresolved", "distance_m": None, "receiving_water": source.get("receiving_water", ""), "confidence": "low", "subbasin_confidence": "low", "coordinate_valid": False, "coordinate_source": coordinate_evidence, "source_crs": str(source_crs or "unknown"), "evidence": "", "manual_confirmation": True}
        x, y = source.get("longitude"), source.get("latitude")
        if source.get("geometry_type") != "point" or pd.isna(x) or pd.isna(y) or source_crs is None:
            row["evidence"] = "Point geometry and explicit CRS required"; rows.append(row); continue
        try:
            if CRS.from_user_input(source_crs).is_geographic and not (-180 <= float(x) <= 180 and -90 <= float(y) <= 90): raise ValueError()
            point = gpd.GeoSeries([Point(float(x), float(y))], crs=source_crs).to_crs(crs).iloc[0]
            if not point.is_valid: raise ValueError()
        except (ValueError, TypeError): rows.append(row); continue
        row["coordinate_valid"] = True
        hits = basins[basins.geometry.covers(point)]
        if len(hits) == 1:
            row["subbasin_id"] = str(hits.iloc[0].subbasin_id)
            row["subbasin_confidence"] = "high" if coordinate_evidence else "low"
        if lines.empty: rows.append(row); continue
        distances = lines.geometry.distance(point)
        explicit = source.get("explicit_reach_id")
        selected = lines[lines.reach_id.eq(explicit)] if explicit and "reach_id" in lines else lines.iloc[0:0]
        method = "explicit" if len(selected) == 1 and source.get("explicit_relation_evidence") else "nearest_reach"
        if method != "explicit":
            name = normalized_water_name(row["receiving_water"], aliases)
            matches = lines[lines.get("name", pd.Series("", index=lines.index)).map(lambda n: normalized_water_name(n, aliases)).eq(name)] if name else lines.iloc[0:0]
            consistent = matches[distances.loc[matches.index] <= near_distance_m]
            if len(consistent) == 1: selected = consistent; method = "receiving_water"
            else: selected = lines.loc[[distances.idxmin()]]
        line = selected.iloc[0]; distance = float(distances.loc[selected.index[0]])
        row.update(candidate_river_line=str(line.get("name", selected.index[0])), distance_m=distance, mapping_method=method)
        reviewed_reach = line.get("reach_id")
        if pd.notna(reviewed_reach) and reviewed_reach:
            row["reach_id"] = str(reviewed_reach)
            if coordinate_evidence and row["subbasin_id"] and method in {"explicit", "receiving_water"}: row["confidence"] = "high"
            elif coordinate_evidence and row["subbasin_id"] and point.intersects(line.geometry): row["confidence"] = "medium"; row["mapping_method"] = "intersection"
        row["evidence"] = json.dumps({"coordinate_evidence": coordinate_evidence, "receiving_water_match": method == "receiving_water", "spatial_consistency": distance <= near_distance_m, "reach_crosswalk_available": row["reach_id"] is not None}, ensure_ascii=False)
        row["manual_confirmation"] = row["confidence"] == "low"
        rows.append(row)
    return pd.DataFrame(rows)
