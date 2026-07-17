from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from functools import lru_cache
import heapq
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any

import pandas as pd

from hydrolite.data_templates import validate_reaches_template, validate_subbasins_template
from hydrolite.qgis_bridge import get_qgis_process_path, qgis_process_algorithms, qgis_process_version, run_qgis_process


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DEM = PROJECT_ROOT / "data_demo" / "gis" / "demo_dem.asc"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "watershed"

_NEIGHBORS = (
    (-1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, -1),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


@lru_cache(maxsize=1)
def _algorithm_inventory() -> dict[str, Any]:
    result = qgis_process_algorithms()
    algorithms = [line.strip() for line in result.get("algorithms", []) if line.strip()]
    return {
        "qgis_process": get_qgis_process_path(),
        "return_code": result.get("return_code"),
        "algorithms": algorithms,
        "stderr": result.get("stderr", ""),
    }


def list_watershed_algorithm_candidates() -> list[dict[str, Any]]:
    inventory = _algorithm_inventory()
    categories = {
        "grass": ["grass:", "r.watershed", "r.fill.dir", "r.water.outlet"],
        "saga": ["saga:"],
        "watershed": ["watershed", "catchment", "basin"],
        "fill_sinks": ["fill sink", "fillsink", "r.fill.dir"],
        "flow_accumulation": ["flow accumulation", "flowaccum", "r.watershed"],
        "stream_network": ["stream network", "extract stream", "channel network"],
        "taudem": ["taudem"],
        "whitebox": ["whitebox"],
    }
    rows: list[dict[str, Any]] = []
    for category, keywords in categories.items():
        matches = [line for line in inventory["algorithms"] if any(word in line.lower() for word in keywords)]
        rows.append(
            {
                "category": category,
                "status": "available" if matches else "unavailable",
                "keywords": ", ".join(keywords),
                "matched_algorithms": matches,
                "match_count": len(matches),
            }
        )
    return rows


def diagnose_grass_runtime() -> dict[str, Any]:
    qgis_root = Path("/Applications/QGIS.app/Contents")
    provider = qgis_root / "Resources" / "qgis" / "python" / "plugins" / "grassprovider"
    bundle_candidates = sorted(qgis_root.glob("MacOS/grass*")) if qgis_root.exists() else []
    standalone_apps = sorted(Path("/Applications").glob("GRASS*.app")) if Path("/Applications").exists() else []
    path_candidates = [shutil.which(name) for name in ("grass", "grass84", "grass83", "grass82", "grass80")]
    executables = [str(Path(path).resolve()) for path in path_candidates if path]
    gisbase = os.environ.get("GISBASE", "")
    gisbase_valid = bool(gisbase and Path(gisbase).is_dir())
    runtime_available = bool(executables or bundle_candidates or standalone_apps or gisbase_valid)
    if provider.exists() and not runtime_available:
        root_cause = (
            "QGIS includes and loads the grassprovider Python plugin, but no GRASS GIS runtime, executable, "
            "standalone GRASS application, or valid GISBASE was found. The provider therefore has algorithm "
            "descriptions but cannot register or execute r.watershed/r.fill.dir/r.water.outlet."
        )
    elif runtime_available:
        root_cause = "A GRASS runtime candidate exists; provider compatibility still requires a qgis_process algorithm check."
    else:
        root_cause = "Neither the QGIS GRASS provider nor a GRASS runtime was detected."
    return {
        "status": "available" if runtime_available else "unavailable",
        "provider_plugin_path": str(provider),
        "provider_plugin_exists": provider.exists(),
        "bundle_runtime_candidates": [str(path) for path in bundle_candidates],
        "standalone_app_candidates": [str(path) for path in standalone_apps],
        "path_executables": executables,
        "gisbase": gisbase,
        "gisbase_valid": gisbase_valid,
        "root_cause": root_cause,
        "recommended_action": (
            "HydroLite will use QGIS native sink filling plus its deterministic D8 topology engine. "
            "A separate GRASS installation can be considered later, but is not required for this MVP."
        ),
    }


def detect_watershed_backends() -> dict[str, Any]:
    inventory = _algorithm_inventory()
    candidates = list_watershed_algorithm_candidates()
    by_category = {row["category"]: row for row in candidates}
    qgis_available = bool(inventory["qgis_process"] and inventory["return_code"] == 0)
    fill_available = by_category["fill_sinks"]["match_count"] > 0
    qgis_accumulation_available = by_category["flow_accumulation"]["match_count"] > 0
    qgis_stream_available = by_category["stream_network"]["match_count"] > 0
    basin_available = by_category["watershed"]["match_count"] > 0
    stable_accumulation_available = fill_available
    stable_stream_available = fill_available

    if qgis_available and fill_available and qgis_accumulation_available and qgis_stream_available and basin_available:
        status = "available"
        message = "qgis_process exposes a complete candidate algorithm chain; results still require GIS review."
    elif qgis_available and (fill_available or stable_accumulation_available or basin_available):
        status = "partial"
        message = (
            "QGIS native sink filling and flow direction are available. HydroLite provides deterministic "
            "topological accumulation and stream extraction; outlet-based basin delineation remains partial."
        )
    elif qgis_available:
        status = "fallback"
        message = "qgis_process is available but no stable watershed chain was detected; use diagnostic fallback outputs."
    else:
        status = "fallback"
        message = "qgis_process is unavailable; the small deterministic Python fallback remains available for workflow testing."

    version = qgis_process_version() if inventory["qgis_process"] else {}
    grass = diagnose_grass_runtime()
    return {
        "status": status,
        "message": message,
        "qgis_process_available": qgis_available,
        "qgis_process_path": inventory["qgis_process"],
        "qgis_version": version.get("stdout", ""),
        "qgis_stderr": inventory["stderr"],
        "grass_diagnosis": grass,
        "capabilities": {
            "fill_sinks": fill_available,
            "qgis_flow_direction": fill_available,
            "qgis_flow_accumulation": qgis_accumulation_available,
            "qgis_stream_network": qgis_stream_available,
            "flow_accumulation": stable_accumulation_available,
            "stream_network": stable_stream_available,
            "basin_delineation": basin_available,
        },
        "algorithm_candidates": candidates,
        "fallback_available": True,
    }


def create_demo_dem(output_path: str | Path) -> Path:
    output = _path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    ncols = 12
    nrows = 12
    center = (ncols - 1) / 2
    values: list[list[float]] = []
    for row in range(nrows):
        row_values = []
        for col in range(ncols):
            elevation = 140.0 + (nrows - row) * 2.4 + abs(col - center) * 1.3
            if 4 <= row <= 7 and 4 <= col <= 7:
                elevation -= 5.5
            if col in {5, 6}:
                elevation -= row * 0.35
            row_values.append(round(elevation, 3))
        values.append(row_values)
    values[6][6] -= 4.0
    _write_ascii_grid(
        output,
        {
            "ncols": ncols,
            "nrows": nrows,
            "xllcorner": 0.0,
            "yllcorner": 0.0,
            "cellsize": 100.0,
            "nodata_value": -9999.0,
            "values": values,
        },
    )
    return output


def _read_ascii_grid(path: str | Path) -> dict[str, Any]:
    grid_path = _path(path)
    lines = grid_path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 7:
        raise ValueError(f"ASCII grid is incomplete: {grid_path}")
    header: dict[str, float] = {}
    for line in lines[:6]:
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"Invalid ASCII grid header line: {line}")
        header[parts[0].lower()] = float(parts[1])
    ncols = int(header["ncols"])
    nrows = int(header["nrows"])
    values = [[float(value) for value in line.split()] for line in lines[6 : 6 + nrows]]
    if len(values) != nrows or any(len(row) != ncols for row in values):
        raise ValueError(f"ASCII grid dimensions do not match header: {grid_path}")
    return {
        "ncols": ncols,
        "nrows": nrows,
        "xllcorner": header.get("xllcorner", header.get("xllcenter", 0.0)),
        "yllcorner": header.get("yllcorner", header.get("yllcenter", 0.0)),
        "cellsize": header["cellsize"],
        "nodata_value": header.get("nodata_value", -9999.0),
        "values": values,
    }


def _write_ascii_grid(path: str | Path, grid: dict[str, Any]) -> Path:
    output = _path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"ncols {grid['ncols']}",
        f"nrows {grid['nrows']}",
        f"xllcorner {grid['xllcorner']}",
        f"yllcorner {grid['yllcorner']}",
        f"cellsize {grid['cellsize']}",
        f"NODATA_value {grid['nodata_value']}",
    ]
    lines.extend(" ".join(f"{float(value):.6f}" for value in row) for row in grid["values"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def inspect_dem(dem_path: str | Path) -> dict[str, Any]:
    path = _path(dem_path)
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "file_size_bytes": path.stat().st_size if path.exists() else 0,
        "raster_format": path.suffix.lower().lstrip(".") or "unknown",
        "ncols": None,
        "nrows": None,
        "nodata_value": None,
        "min_elevation": None,
        "max_elevation": None,
        "qgis_recognized": False,
        "qgis_message": "",
        "warnings": [],
        "errors": [],
    }
    if not path.exists():
        result["errors"].append(f"DEM not found: {path}")
        return result
    if path.suffix.lower() in {".asc", ".txt"}:
        try:
            grid = _read_ascii_grid(path)
            valid = [value for row in grid["values"] for value in row if value != grid["nodata_value"]]
            result.update(
                {
                    "ncols": grid["ncols"],
                    "nrows": grid["nrows"],
                    "nodata_value": grid["nodata_value"],
                    "min_elevation": min(valid) if valid else None,
                    "max_elevation": max(valid) if valid else None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(str(exc))
    else:
        result["warnings"].append("Lightweight parser only reads ASCII grid metadata; QGIS may still recognize this raster.")

    if get_qgis_process_path():
        qgis = run_qgis_process(["run", "native:rasterlayerstatistics", "--", f"INPUT={path}", "BAND=1"], timeout=45)
        result["qgis_recognized"] = qgis.get("return_code") == 0
        result["qgis_message"] = qgis.get("stdout") or qgis.get("stderr") or ""
        if not result["qgis_recognized"]:
            result["warnings"].append("qgis_process could not read the DEM; lightweight inspection was used.")
    else:
        result["warnings"].append("qgis_process is unavailable; QGIS recognition was not tested.")
    return result


def _priority_fill(grid: dict[str, Any], epsilon: float = 0.001) -> dict[str, Any]:
    values = [row[:] for row in grid["values"]]
    rows = grid["nrows"]
    cols = grid["ncols"]
    visited = [[False] * cols for _ in range(rows)]
    heap: list[tuple[float, int, int]] = []
    for row in range(rows):
        for col in range(cols):
            if row in {0, rows - 1} or col in {0, cols - 1}:
                heapq.heappush(heap, (values[row][col], row, col))
                visited[row][col] = True
    while heap:
        elevation, row, col = heapq.heappop(heap)
        for drow, dcol in _NEIGHBORS:
            nr, nc = row + drow, col + dcol
            if not (0 <= nr < rows and 0 <= nc < cols) or visited[nr][nc]:
                continue
            visited[nr][nc] = True
            raised = max(values[nr][nc], elevation + epsilon)
            values[nr][nc] = raised
            heapq.heappush(heap, (raised, nr, nc))
    return {**grid, "values": values}


def run_fill_sinks(dem_path: str | Path, output_path: str | Path, backend: str = "auto") -> dict[str, Any]:
    source = _path(dem_path)
    output = _path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
    candidates = list_watershed_algorithm_candidates()
    fill_matches = next(row["matched_algorithms"] for row in candidates if row["category"] == "fill_sinks")
    qgis_fill = next((line.split()[0] for line in fill_matches if "native:fillsinkswangliu" in line), None)
    if backend in {"auto", "qgis_process"} and qgis_fill:
        qgis_filled = output if output.suffix.lower() in {".tif", ".tiff"} else output.with_name(f"{output.stem}_qgis.tif")
        flow_direction_tif = output.with_name("flow_directions.tif")
        flow_direction_asc = output.with_name("flow_directions.asc")
        result = run_qgis_process(
            [
                "run",
                "native:fillsinkswangliu",
                "--",
                f"INPUT={source}",
                "BAND=1",
                "MIN_SLOPE=0.1",
                f"OUTPUT_FILLED_DEM={qgis_filled}",
                f"OUTPUT_FLOW_DIRECTIONS={flow_direction_tif}",
                f"OUTPUT_WATERSHED_BASINS={output.with_name('watershed_basins.tif')}",
            ],
            timeout=90,
        )
        attempts.append(
            {
                "backend": "qgis_process:native:fillsinkswangliu",
                "status": "success" if result.get("return_code") == 0 and qgis_filled.exists() else "failed",
                "return_code": result.get("return_code"),
                "message": result.get("stderr") or result.get("stdout") or "",
            }
        )
        if result.get("return_code") == 0 and qgis_filled.exists():
            if qgis_filled != output:
                translate = run_qgis_process(
                    ["run", "gdal:translate", "--", f"INPUT={qgis_filled}", "DATA_TYPE=7", f"OUTPUT={output}"],
                    timeout=60,
                )
                attempts.append(
                    {
                        "backend": "qgis_process:gdal:translate",
                        "status": "success" if translate.get("return_code") == 0 and output.exists() else "failed",
                        "return_code": translate.get("return_code"),
                        "message": translate.get("stderr") or translate.get("stdout") or "",
                    }
                )
            if flow_direction_tif.exists():
                direction_translate = run_qgis_process(
                    ["run", "gdal:translate", "--", f"INPUT={flow_direction_tif}", "DATA_TYPE=5", f"OUTPUT={flow_direction_asc}"],
                    timeout=60,
                )
                attempts.append(
                    {
                        "backend": "qgis_process:gdal:translate:flow_directions",
                        "status": "success" if direction_translate.get("return_code") == 0 and flow_direction_asc.exists() else "failed",
                        "return_code": direction_translate.get("return_code"),
                        "message": direction_translate.get("stderr") or direction_translate.get("stdout") or "",
                    }
                )
            if output.exists():
                return {
                    "status": "success",
                    "method": "qgis_process:native:fillsinkswangliu",
                    "output": str(output),
                    "qgis_raster": str(qgis_filled),
                    "flow_directions": str(flow_direction_asc) if flow_direction_asc.exists() else "",
                    "attempts": attempts,
                }
        if backend == "qgis_process":
            return {"status": "failed", "method": "qgis_process", "output": str(output), "attempts": attempts}
    try:
        filled = _priority_fill(_read_ascii_grid(source))
        _write_ascii_grid(output, filled)
        attempts.append(
            {
                "backend": "python_priority_flood_fallback",
                "status": "success",
                "return_code": 0,
                "message": "Small deterministic fallback for workflow verification; not a professional GIS delineation result.",
            }
        )
        return {"status": "success", "method": "python_priority_flood_fallback", "output": str(output), "attempts": attempts}
    except Exception as exc:  # noqa: BLE001
        attempts.append({"backend": "python_priority_flood_fallback", "status": "failed", "return_code": 1, "message": str(exc)})
        return {"status": "failed", "method": "python_priority_flood_fallback", "output": str(output), "attempts": attempts}


def _accumulate_downstream(rows: int, cols: int, downstream: list[list[int | None]]) -> list[list[float]]:
    indegree = [0] * (rows * cols)
    for row in range(rows):
        for col in range(cols):
            target = downstream[row][col]
            if target is not None:
                indegree[target] += 1
    accumulation = [1.0] * (rows * cols)
    queue = deque(index for index, degree in enumerate(indegree) if degree == 0)
    processed = 0
    while queue:
        index = queue.popleft()
        processed += 1
        row, col = divmod(index, cols)
        target = downstream[row][col]
        if target is None:
            continue
        accumulation[target] += accumulation[index]
        indegree[target] -= 1
        if indegree[target] == 0:
            queue.append(target)
    if processed != rows * cols:
        raise ValueError("Flow direction grid contains a cycle; accumulation cannot be resolved safely.")
    return [accumulation[row * cols : (row + 1) * cols] for row in range(rows)]


def _downstream_from_direction_grid(grid: dict[str, Any]) -> list[list[int | None]]:
    rows, cols = grid["nrows"], grid["ncols"]
    downstream: list[list[int | None]] = [[None] * cols for _ in range(rows)]
    nodata = grid["nodata_value"]
    for row in range(rows):
        for col in range(cols):
            value = grid["values"][row][col]
            if value == nodata:
                continue
            code = int(round(value))
            if not 0 <= code < len(_NEIGHBORS):
                continue
            drow, dcol = _NEIGHBORS[code]
            nr, nc = row + drow, col + dcol
            if 0 <= nr < rows and 0 <= nc < cols:
                downstream[row][col] = nr * cols + nc
    return downstream


def _repair_flow_cycles(
    downstream: list[list[int | None]],
    rows: int,
    cols: int,
    elevations: list[list[float]],
) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    for start in range(rows * cols):
        current: int | None = start
        path: list[int] = []
        positions: dict[int, int] = {}
        while current is not None:
            if current in positions:
                cycle = path[positions[current] :]
                boundary = [
                    index
                    for index in cycle
                    if (index // cols) in {0, rows - 1} or (index % cols) in {0, cols - 1}
                ]
                candidates = boundary or cycle
                outlet = min(candidates, key=lambda index: elevations[index // cols][index % cols])
                downstream[outlet // cols][outlet % cols] = None
                repairs.append(
                    {
                        "cycle_cells": [[index // cols, index % cols] for index in cycle],
                        "outlet_cell": [outlet // cols, outlet % cols],
                        "reason": "boundary_lowest_cell" if boundary else "cycle_lowest_elevation_cell",
                    }
                )
                break
            positions[current] = len(path)
            path.append(current)
            current = downstream[current // cols][current % cols]
    return repairs


def _d8_accumulation(grid: dict[str, Any]) -> tuple[list[list[float]], list[list[int | None]]]:
    values = grid["values"]
    rows, cols = grid["nrows"], grid["ncols"]
    downstream: list[list[int | None]] = [[None] * cols for _ in range(rows)]
    for row in range(rows):
        for col in range(cols):
            best: tuple[float, int] | None = None
            for drow, dcol in _NEIGHBORS:
                nr, nc = row + drow, col + dcol
                if not (0 <= nr < rows and 0 <= nc < cols):
                    continue
                distance = math.sqrt(2.0) if drow and dcol else 1.0
                slope = (values[row][col] - values[nr][nc]) / distance
                if slope > 0 and (best is None or slope > best[0]):
                    best = (slope, nr * cols + nc)
            if best:
                downstream[row][col] = best[1]
    return _accumulate_downstream(rows, cols, downstream), downstream


def run_flow_accumulation(dem_path: str | Path, output_dir: str | Path, backend: str = "auto") -> dict[str, Any]:
    source = _path(dem_path)
    output = _path(output_dir) / "flow_accumulation.asc"
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        grid = _read_ascii_grid(source)
        direction_path = output.parent / "flow_directions.asc"
        if direction_path.exists():
            direction_grid = _read_ascii_grid(direction_path)
            if (direction_grid["nrows"], direction_grid["ncols"]) != (grid["nrows"], grid["ncols"]):
                raise ValueError("Flow direction and DEM grid dimensions do not match.")
            downstream = _downstream_from_direction_grid(direction_grid)
            cycle_repairs = _repair_flow_cycles(downstream, grid["nrows"], grid["ncols"], grid["values"])
            accumulation = _accumulate_downstream(grid["nrows"], grid["ncols"], downstream)
            method = "qgis_d8_direction_plus_hydrolite_topology"
        else:
            accumulation, downstream = _d8_accumulation(grid)
            cycle_repairs = []
            method = "hydrolite_d8_topology"
        _write_ascii_grid(output, {**grid, "values": accumulation})
        return {
            "status": "success",
            "method": method,
            "output": str(output),
            "flow_directions": str(direction_path) if direction_path.exists() else "derived_from_filled_dem",
            "max_accumulation_cells": max(value for row in accumulation for value in row),
            "cycle_repairs": cycle_repairs,
            "cycle_repair_count": len(cycle_repairs),
            "warning": "GRASS is unavailable; accumulation uses a deterministic acyclic D8 topology engine.",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "method": "hydrolite_d8_topology", "output": str(output), "error": str(exc)}


def _cell_center(grid: dict[str, Any], row: int, col: int) -> list[float]:
    x = grid["xllcorner"] + (col + 0.5) * grid["cellsize"]
    y = grid["yllcorner"] + (grid["nrows"] - row - 0.5) * grid["cellsize"]
    return [x, y]


def extract_stream_network(
    flow_accumulation_path: str | Path,
    output_path: str | Path,
    threshold: float | None = None,
    backend: str = "auto",
) -> dict[str, Any]:
    source = _path(flow_accumulation_path)
    output = _path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        grid = _read_ascii_grid(source)
        values = grid["values"]
        flat = [value for row in values for value in row]
        chosen_threshold = float(threshold if threshold is not None else max(4.0, round(max(flat) * 0.18, 2)))
        direction_path = source.parent / "flow_directions.asc"
        direction_grid = _read_ascii_grid(direction_path) if direction_path.exists() else None
        downstream = _downstream_from_direction_grid(direction_grid) if direction_grid else None
        cycle_repairs: list[dict[str, Any]] = []
        if downstream:
            filled_dem = source.parent / "filled_dem.asc"
            elevations = _read_ascii_grid(filled_dem)["values"] if filled_dem.exists() else values
            cycle_repairs = _repair_flow_cycles(downstream, grid["nrows"], grid["ncols"], elevations)
        method = "qgis_d8_direction_plus_hydrolite_stream_extraction" if downstream else "hydrolite_accumulation_gradient_stream_extraction"
        features = []
        for row in range(grid["nrows"]):
            for col in range(grid["ncols"]):
                if values[row][col] < chosen_threshold:
                    continue
                target = downstream[row][col] if downstream else None
                if target is not None:
                    nr, nc = divmod(target, grid["ncols"])
                else:
                    larger: list[tuple[float, int, int]] = []
                    for drow, dcol in _NEIGHBORS:
                        candidate_row, candidate_col = row + drow, col + dcol
                        if (
                            0 <= candidate_row < grid["nrows"]
                            and 0 <= candidate_col < grid["ncols"]
                            and values[candidate_row][candidate_col] > values[row][col]
                        ):
                            larger.append((values[candidate_row][candidate_col], candidate_row, candidate_col))
                    if not larger:
                        continue
                    _, nr, nc = max(larger)
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "segment_id": f"SEG_{len(features) + 1}",
                            "accumulation_cells": values[row][col],
                            "threshold_cells": chosen_threshold,
                            "processing_method": method,
                            "is_fallback": downstream is None,
                            "review_required": True,
                        },
                        "geometry": {"type": "LineString", "coordinates": [_cell_center(grid, row, col), _cell_center(grid, nr, nc)]},
                    }
                )
        if not features:
            center = grid["ncols"] // 2
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "segment_id": "SEG_1",
                        "accumulation_cells": max(flat),
                        "threshold_cells": chosen_threshold,
                        "processing_method": "fallback_example_axis",
                        "is_fallback": True,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [_cell_center(grid, 0, center), _cell_center(grid, grid["nrows"] - 1, center)],
                    },
                }
            )
        output.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2) + "\n", encoding="utf-8")
        return {
            "status": "success",
            "method": method,
            "output": str(output),
            "threshold": chosen_threshold,
            "feature_count": len(features),
            "cycle_repairs": cycle_repairs,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "method": "hydrolite_stream_extraction", "output": str(output), "error": str(exc)}


def _polygon_feature(feature_id: str, coordinates: list[list[float]], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {"id": feature_id, **properties},
        "geometry": {"type": "Polygon", "coordinates": [[*coordinates, coordinates[0]]]},
    }


def _write_hydrolite_templates(output_dir: Path) -> dict[str, str]:
    subbasins = output_dir / "hydrolite_subbasins.csv"
    reaches = output_dir / "hydrolite_reaches.csv"
    pd.DataFrame(
        [
            {"subbasin_id": "S1", "area_km2": 0.72, "cn": 75, "initial_abstraction_ratio": 0.2, "lag_time_hr": 0.5, "outlet_reach_id": "R1"},
            {"subbasin_id": "S2", "area_km2": 0.72, "cn": 75, "initial_abstraction_ratio": 0.2, "lag_time_hr": 0.5, "outlet_reach_id": "R2"},
        ]
    ).to_csv(subbasins, index=False)
    pd.DataFrame(
        [
            {"reach_id": "R1", "upstream_reach_id": "", "downstream_reach_id": "R2", "length_km": 0.6, "slope": 0.02, "muskingum_k_hr": 1.0, "muskingum_x": 0.2},
            {"reach_id": "R2", "upstream_reach_id": "R1", "downstream_reach_id": "", "length_km": 0.6, "slope": 0.015, "muskingum_k_hr": 1.0, "muskingum_x": 0.2},
        ]
    ).to_csv(reaches, index=False)
    return {"hydrolite_subbasins_csv": str(subbasins), "hydrolite_reaches_csv": str(reaches)}


def delineate_basin(
    dem_path: str | Path,
    outlet_point: tuple[float, float] | None = None,
    output_dir: str | Path = "output/watershed",
    backend: str = "auto",
) -> dict[str, Any]:
    output = _path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    grid = _read_ascii_grid(dem_path)
    x0, y0 = grid["xllcorner"], grid["yllcorner"]
    x1 = x0 + grid["ncols"] * grid["cellsize"]
    y1 = y0 + grid["nrows"] * grid["cellsize"]
    xm = (x0 + x1) / 2
    base_properties = {
        "processing_method": "synthetic_extent_fallback",
        "is_fallback": True,
        "review_required": True,
        "note": "MVP example geometry derived from the synthetic DEM extent; not a surveyed basin boundary.",
    }
    basin = {
        "type": "FeatureCollection",
        "features": [_polygon_feature("BASIN_1", [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], base_properties)],
    }
    subbasins = {
        "type": "FeatureCollection",
        "features": [
            _polygon_feature("S1", [[x0, y0], [xm, y0], [xm, y1], [x0, y1]], {**base_properties, "subbasin_id": "S1"}),
            _polygon_feature("S2", [[xm, y0], [x1, y0], [x1, y1], [xm, y1]], {**base_properties, "subbasin_id": "S2"}),
        ],
    }
    basin_path = output / "basin_boundary.geojson"
    subbasins_path = output / "subbasins.geojson"
    basin_path.write_text(json.dumps(basin, indent=2) + "\n", encoding="utf-8")
    subbasins_path.write_text(json.dumps(subbasins, indent=2) + "\n", encoding="utf-8")
    templates = _write_hydrolite_templates(output)
    return {
        "status": "fallback",
        "method": "synthetic_extent_fallback",
        "outlet_point": list(outlet_point) if outlet_point else [xm, y0],
        "basin_boundary": str(basin_path),
        "subbasins": str(subbasins_path),
        **templates,
        "warning": "Current environment did not provide a stable outlet-based delineation chain; example geometry requires GIS review.",
    }


def _backend_rows(backends: dict[str, Any], steps: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {
            "component": "qgis_process",
            "status": "available" if backends["qgis_process_available"] else "unavailable",
            "backend": backends.get("qgis_process_path") or "",
            "details": backends.get("qgis_version") or backends.get("message", ""),
        }
    ]
    grass = backends.get("grass_diagnosis", {})
    rows.append(
        {
            "component": "grass_runtime",
            "status": grass.get("status", "unavailable"),
            "backend": grass.get("path_executables", []),
            "details": grass.get("root_cause", ""),
        }
    )
    for name, value in steps.items():
        rows.append(
            {
                "component": name,
                "status": value.get("status", "unknown"),
                "backend": value.get("method", ""),
                "details": value.get("warning") or value.get("error") or "",
            }
        )
    return pd.DataFrame(rows)


def run_watershed_mvp(dem_path: str | Path | None = None, output_dir: str | Path = "output/watershed") -> dict[str, Any]:
    output = _path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if dem_path is None:
        demo_source = create_demo_dem(DEFAULT_DEMO_DEM)
        working_dem = output / "demo_dem.asc"
        shutil.copy2(demo_source, working_dem)
    else:
        source = _path(dem_path)
        working_dem = output / source.name
        if source != working_dem:
            shutil.copy2(source, working_dem)

    backends = detect_watershed_backends()
    inspection = inspect_dem(working_dem)
    fill = run_fill_sinks(working_dem, output / "filled_dem.asc")
    accumulation_source = Path(fill["output"]) if fill["status"] == "success" else working_dem
    analysis_warning = ""
    try:
        _read_ascii_grid(accumulation_source)
    except Exception as exc:  # noqa: BLE001
        accumulation_source = create_demo_dem(output / "fallback_demo_dem.asc")
        analysis_warning = (
            f"The supplied DEM could not be converted to a readable ASCII grid ({exc}); "
            "remaining fallback products use the synthetic demo DEM and are not results for the supplied raster."
        )
    accumulation = run_flow_accumulation(accumulation_source, output)
    stream = (
        extract_stream_network(accumulation["output"], output / "stream_network.geojson")
        if accumulation["status"] == "success"
        else {
            "status": "failed",
            "method": "not_run",
            "output": str(output / "stream_network.geojson"),
            "error": "Flow accumulation failed; stream extraction was not run to avoid stale outputs.",
        }
    )
    basin = delineate_basin(accumulation_source, output_dir=output)
    steps = {"fill_sinks": fill, "flow_accumulation": accumulation, "stream_network": stream, "basin_delineation": basin}
    status = backends["status"]
    if fill.get("method", "").startswith("python"):
        status = "fallback"
    result = {
        "generated_at": _now(),
        "status": status,
        "mvp_only": True,
        "professional_review_required": True,
        "message": (
            "Current environment has only a partial stable watershed backend; generated outputs combine qgis_process and clearly marked fallback steps."
            if status == "partial"
            else "Current environment did not expose a stable watershed backend; generated diagnostic and simplified fallback outputs only."
        ),
        "analysis_warning": analysis_warning,
        "output_dir": str(output),
        "dem": str(working_dem),
        "dem_inspection": inspection,
        "backends": backends,
        "steps": steps,
        "outputs": {
            "demo_dem": str(working_dem),
            "filled_dem": fill["output"],
            "flow_directions": fill.get("flow_directions", ""),
            "flow_accumulation": accumulation["output"],
            "stream_network": stream["output"],
            "basin_boundary": basin["basin_boundary"],
            "subbasins": basin["subbasins"],
            "hydrolite_subbasins": basin["hydrolite_subbasins_csv"],
            "hydrolite_reaches": basin["hydrolite_reaches_csv"],
        },
    }
    diagnosis = output / "watershed_diagnosis.json"
    diagnosis.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result["outputs"]["diagnosis"] = str(diagnosis)
    backend_xlsx = output / "watershed_backend_summary.xlsx"
    with pd.ExcelWriter(backend_xlsx) as writer:
        _backend_rows(backends, steps).to_excel(writer, sheet_name="backend_summary", index=False)
        pd.DataFrame(backends["algorithm_candidates"]).assign(
            matched_algorithms=lambda frame: frame["matched_algorithms"].apply(lambda value: "; ".join(value))
        ).to_excel(writer, sheet_name="algorithm_candidates", index=False)
    result["outputs"]["backend_summary"] = str(backend_xlsx)
    validation = validate_watershed_outputs(output)
    result["validation"] = validation
    result["outputs"]["report"] = str(write_watershed_report(output, result))
    diagnosis.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def validate_watershed_outputs(output_dir: str | Path) -> dict[str, Any]:
    output = _path(output_dir)
    required = [
        "watershed_diagnosis.json",
        "watershed_backend_summary.xlsx",
        "flow_directions.asc",
        "flow_accumulation.asc",
        "basin_boundary.geojson",
        "stream_network.geojson",
        "subbasins.geojson",
        "hydrolite_subbasins.csv",
        "hydrolite_reaches.csv",
    ]
    checks = [{"name": name, "path": str(output / name), "exists": (output / name).exists()} for name in required]
    subbasins_validation = validate_subbasins_template(output / "hydrolite_subbasins.csv")
    reaches_validation = validate_reaches_template(output / "hydrolite_reaches.csv")
    missing = [check["name"] for check in checks if not check["exists"]]
    status = "failed" if missing or "failed" in {subbasins_validation["status"], reaches_validation["status"]} else "passed"
    warnings = []
    diagnosis_path = output / "watershed_diagnosis.json"
    if diagnosis_path.exists():
        diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
        if diagnosis.get("status") in {"partial", "fallback", "unavailable"}:
            warnings.append("Watershed outputs are MVP/fallback products and require professional GIS review.")
    return {
        "status": status,
        "output_dir": str(output),
        "checks": checks,
        "missing": missing,
        "warnings": warnings,
        "data_template_validation": {"subbasins": subbasins_validation, "reaches": reaches_validation},
    }


def write_watershed_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    output = _path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = output / "watershed_report.md"
    backends = result.get("backends", {})
    inspection = result.get("dem_inspection", {})
    steps = result.get("steps", {})
    validation = result.get("validation") or validate_watershed_outputs(output)
    grass = backends.get("grass_diagnosis", {})
    lines = [
        "# HydroLite Watershed Delineation MVP Report",
        "",
        "> 当前为流域划分 MVP，用于验证工作流和环境，不替代专业 GIS 人工复核。",
        "",
        "## Summary",
        "",
        f"- Status: `{result.get('status', 'unknown')}`",
        f"- Output directory: `{output}`",
        f"- DEM: `{result.get('dem', '')}`",
        f"- qgis_process: `{backends.get('qgis_process_path') or 'unavailable'}`",
        f"- QGIS version: `{backends.get('qgis_version') or 'unavailable'}`",
        f"- Validation: `{validation.get('status', 'unknown')}`",
        "- Backend note: `QGIS 填洼/流向 + HydroLite 无环 D8 拓扑汇流/河网已可用；真实出口点流域划分仍为 partial。`",
        "",
        "## GRASS Diagnosis",
        "",
        f"- GRASS status: `{grass.get('status', 'unavailable')}`",
        f"- Provider plugin exists: `{grass.get('provider_plugin_exists', False)}`",
        f"- GISBASE valid: `{grass.get('gisbase_valid', False)}`",
        f"- Root cause: {grass.get('root_cause', 'not checked')}",
        "",
        "## DEM Inspection",
        "",
        f"- Size: `{inspection.get('ncols')} x {inspection.get('nrows')}`",
        f"- Elevation range: `{inspection.get('min_elevation')} - {inspection.get('max_elevation')}`",
        f"- QGIS recognized: `{inspection.get('qgis_recognized')}`",
        "",
        "## Processing Steps",
        "",
        "| Step | Status | Method | Note |",
        "| --- | --- | --- | --- |",
    ]
    for name, step in steps.items():
        note = str(step.get("warning") or step.get("error") or "").replace("|", "/")
        lines.append(f"| {name} | {step.get('status', '')} | {step.get('method', '')} | {note} |")
    lines.extend(
        [
            "",
            "## Output Files",
            "",
        ]
    )
    for name, path in result.get("outputs", {}).items():
        lines.append(f"- {name}: `{path}`")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- 本次 demo DEM 使用无敏感地理含义的合成局部坐标。",
            "- 汇流累积和河网使用 QGIS D8 流向 + HydroLite 无环拓扑链；河网阈值仍需人工论证。",
            "- 真实出口点吸附、流域边界和子流域划分仍是 fallback 示例。",
            "- 输出不能替代投影检查、出口点校正、阈值论证、地形修正和专业 GIS 人工复核。",
            "- 真实项目应在 QGIS 中检查 DEM 坐标系、分辨率、NoData、洼地处理、河网连通性和面积。",
            "",
            "## Next Step",
            "",
            "将 `hydrolite_subbasins.csv`、`hydrolite_reaches.csv` 与项目降雨数据一起送入数据模板校验和 QGIS -> HydroLite 项目工作流。",
        ]
    )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
