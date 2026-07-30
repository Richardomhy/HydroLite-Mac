from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd


BLOCK_HEADERS = {
    "Project",
    "Basin",
    "Precipitation",
    "Meteorology",
    "Control",
    "Run",
    "Subbasin",
    "Reach",
    "Junction",
    "Reservoir",
    "Sink",
    "Source",
    "Diversion",
    "Gage",
    "Gage Manager",
    "Precip Method Parameters",
}


def format_reservoir_outflow_curve(curve: pd.DataFrame) -> str:
    """Render a reviewable paired-data note; final HMS syntax still needs HMS validation."""
    required = {"stage_m", "discharge_cms"}
    if not required.issubset(curve.columns):
        raise ValueError("Reservoir outflow curve requires stage_m and discharge_cms.")
    rows = ["Paired Data: HydroLite Outflow Curve", "     Type: Elevation-Discharge"]
    rows.extend(f"     {float(row.stage_m):.3f}, {float(row.discharge_cms):.6f}" for _, row in curve.iterrows())
    return "\n".join(rows) + "\n"


def discover_hms_paired_data_files(project_dir: str | Path) -> list[Path]:
    root=Path(project_dir).expanduser().resolve();return [p for p in root.iterdir() if p.is_file() and p.suffix.lower() not in {'.hms','.basin','.run','.met','.control','.dss','.out','.log'} and 'pdata' in p.name.lower()]
def parse_hms_paired_data_file(path: str | Path) -> dict[str, Any]:
    lines=Path(path).read_text(encoding='utf-8',errors='replace').splitlines();blocks=[];current=None
    for line in lines:
        if line.startswith('Table:'):
            if current: blocks.append(current)
            current={'header':line,'name':line.split(':',1)[1].strip(),'lines':[line],'properties':{},'raw_sections':[],'unknown_lines':[]}
        elif current and line.strip()=='End:': current['lines'].append(line);blocks.append(current);current=None
        elif current:
            current['lines'].append(line)
            if ':' in line and line.startswith('     '): key,value=line.strip().split(':',1);current['properties'][key.strip()]=value.strip()
            elif line.strip(): current['unknown_lines'].append(line)
    if current: blocks.append(current)
    return {'path':str(path),'blocks':blocks,'raw_sections':lines}
def _function(path_or_block: str | Path | dict[str,Any], expected:str)->dict[str,Any]:
    parsed=parse_hms_paired_data_file(path_or_block) if not isinstance(path_or_block,dict) else path_or_block
    blocks=parsed.get('blocks',[parsed]);return {'status':'found' if any(expected.lower() in str(b.get('properties',{}).get('Table Type','')).lower() for b in blocks) else 'missing','blocks':[b for b in blocks if expected.lower() in str(b.get('properties',{}).get('Table Type','')).lower()]}
def parse_storage_discharge_function(path_or_block): return _function(path_or_block,'storage')
def parse_elevation_storage_function(path_or_block): return _function(path_or_block,'elevation-storage')
def parse_elevation_area_function(path_or_block): return _function(path_or_block,'elevation-area')
def parse_reservoir_basin_block(path_or_block: str | Path)->dict[str,Any]:
    text=Path(path_or_block).read_text(encoding='utf-8',errors='replace') if isinstance(path_or_block,(str,Path)) else str(path_or_block);start=text.find('Reservoir:');end=text.find('\nEnd:',start);raw=text[start:end+5] if start>=0 else '';return {'status':'found' if raw else 'missing','raw_section':raw,'properties':{line.strip().split(':',1)[0]:line.strip().split(':',1)[1].strip() for line in raw.splitlines() if ':' in line and not line.startswith('Reservoir:')}}
def resolve_hms_paired_data_references(project_dir: str | Path)->dict[str,Any]:
    root=Path(project_dir).expanduser().resolve();files=discover_hms_paired_data_files(root);basins=list(root.glob('*.basin'));return {'paired_files':[str(x) for x in files],'parsed':[parse_hms_paired_data_file(x) for x in files],'reservoir_blocks':[parse_reservoir_basin_block(x) for x in basins]}
def compare_reservoir_generated_to_reference(reference_dir,generated_dir)->dict[str,Any]:
    return {'reference':resolve_hms_paired_data_references(reference_dir),'generated':resolve_hms_paired_data_references(generated_dir),'status':'review_required'}
def validate_hms_413_reservoir_semantics(project_dir)->dict[str,Any]:
    found=resolve_hms_paired_data_references(project_dir);has_res=any(x['status']=='found' for x in found['reservoir_blocks']);return {'status':'passed' if has_res and found['paired_files'] else 'failed','reservoir_element_discovered':has_res,'paired_data_registered':bool(found['paired_files']),'details':found}
def write_hms_reservoir_format_comparison(output_dir,result)->dict[str,Path]:
    root=Path(output_dir).expanduser().resolve();root.mkdir(parents=True,exist_ok=True);j=root/'reservoir_format_comparison.json';m=root/'reservoir_format_comparison.md';j.write_text(json.dumps(result,indent=2,default=str));m.write_text('# HEC-HMS 4.13 Reservoir format comparison\n\nStatus: `%s`. Unknown lines are retained in JSON.\n'%result.get('status','review_required'));return {'json':j,'markdown':m}


def _parse_component(path: str | Path, expected_type: str) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    blocks: list[dict[str, Any]] = []
    unknown_lines: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            if current is not None:
                current["raw_lines"].append(line)
            continue
        if not line[:1].isspace() and ":" in stripped and not stripped.lower().startswith("end:"):
            key, value = stripped.split(":", 1)
            if key in BLOCK_HEADERS:
                if current is not None:
                    current["closed"] = False
                    blocks.append(current)
                current = {
                    "block_type": key,
                    "name": value.strip(),
                    "header_line": line_number,
                    "properties": [],
                    "property_map": {},
                    "raw_lines": [line],
                    "unknown_lines": [],
                    "closed": False,
                }
                continue
        if stripped.lower() == "end:":
            if current is None:
                unknown_lines.append({"line": line_number, "text": line})
            else:
                current["raw_lines"].append(line)
                current["closed"] = True
                blocks.append(current)
                current = None
            continue
        if current is not None:
            current["raw_lines"].append(line)
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                entry = {"key": key.strip(), "value": value.strip(), "line": line_number}
                current["properties"].append(entry)
                current["property_map"].setdefault(entry["key"], []).append(entry["value"])
            else:
                entry = {"line": line_number, "text": line}
                current["unknown_lines"].append(entry)
                unknown_lines.append(entry)
        else:
            unknown_lines.append({"line": line_number, "text": line})
    if current is not None:
        current["closed"] = False
        blocks.append(current)
    header = blocks[0] if blocks else None
    metadata_keys = ("Version", "Description", "Last Modified Date", "Last Modified Time", "Unit System")
    metadata = {
        key: (header.get("property_map", {}).get(key, [""])[0] if header else "")
        for key in metadata_keys
    }
    return {
        "path": str(file_path),
        "file_name": file_path.name,
        "expected_type": expected_type,
        "header": {"block_type": header["block_type"], "name": header["name"]} if header else None,
        "metadata": metadata,
        "blocks": blocks,
        "block_types": [block["block_type"] for block in blocks],
        "unknown_lines": unknown_lines,
        "raw_sections": [block["raw_lines"] for block in blocks],
        "line_count": len(lines),
    }


def parse_hms_project_file(path: str | Path) -> dict[str, Any]:
    return _parse_component(path, "Project")


def parse_hms_basin_file(path: str | Path) -> dict[str, Any]:
    return _parse_component(path, "Basin")


def parse_hms_meteorologic_file(path: str | Path) -> dict[str, Any]:
    return _parse_component(path, "Meteorology")


def parse_hms_control_file(path: str | Path) -> dict[str, Any]:
    return _parse_component(path, "Control")


def parse_hms_run_file(path: str | Path) -> dict[str, Any]:
    return _parse_component(path, "Run")


def _parser_for_suffix(path: Path):
    return {
        ".hms": parse_hms_project_file,
        ".basin": parse_hms_basin_file,
        ".met": parse_hms_meteorologic_file,
        ".control": parse_hms_control_file,
        ".run": parse_hms_run_file,
    }.get(path.suffix.lower())


def inspect_hms_component_headers(project_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(project_dir).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*")):
        parser = _parser_for_suffix(path)
        if not parser or not path.is_file():
            continue
        parsed = parser(path)
        rows.append(
            {
                "file": str(path),
                "suffix": path.suffix.lower(),
                "header_type": (parsed["header"] or {}).get("block_type", ""),
                "component_name": (parsed["header"] or {}).get("name", ""),
                **parsed["metadata"],
                "block_count": len(parsed["blocks"]),
                "unknown_line_count": len(parsed["unknown_lines"]),
            }
        )
    return rows


def inspect_hms_component_references(project_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(project_dir).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*")):
        parser = _parser_for_suffix(path)
        if not parser or not path.is_file():
            continue
        parsed = parser(path)
        for block in parsed["blocks"]:
            for item in block["properties"]:
                if item["key"] in {"Filename", "FileName", "Basin", "Precip", "Precipitation", "Control", "DSS File", "DSS File Name", "Log File"}:
                    target = item["value"]
                    path_like = item["key"] in {"Filename", "FileName", "DSS File", "DSS File Name", "Log File"}
                    rows.append(
                        {
                            "source_file": str(path),
                            "source_block": block["block_type"],
                            "source_name": block["name"],
                            "reference_type": item["key"],
                            "reference_value": target,
                            "target_exists": (root / target).exists() if path_like else None,
                        }
                    )
    return rows


def validate_hms_component_syntax(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    expected = {".hms": "Project", ".basin": "Basin", ".met": "Meteorology", ".control": "Control", ".run": "Run"}
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    for suffix, expected_header in expected.items():
        paths = sorted(root.glob(f"*{suffix}"))
        if not paths:
            errors.append(f"Missing {suffix} component file in project root.")
            continue
        for path in paths:
            parsed = _parser_for_suffix(path)(path)
            header_type = (parsed["header"] or {}).get("block_type")
            closed = all(block["closed"] for block in parsed["blocks"])
            passed = header_type == expected_header and closed
            checks.append({"file": str(path), "expected_header": expected_header, "actual_header": header_type, "blocks_closed": closed, "passed": passed})
            if not passed:
                errors.append(f"Invalid {suffix} structure: {path.name}")
            if parsed["unknown_lines"]:
                warnings.append(f"{path.name} contains {len(parsed['unknown_lines'])} unrecognized lines; they were preserved.")
    references = inspect_hms_component_references(root)
    for reference in references:
        if reference["target_exists"] is False and reference["reference_type"] in {"Filename", "FileName"}:
            errors.append(f"Missing referenced component: {reference['reference_value']}")
    run_names = [row["component_name"] for row in inspect_hms_component_headers(root) if row["header_type"] == "Run"]
    return {
        "status": "passed" if not errors else "failed",
        "project_dir": str(root),
        "checks": checks,
        "references": references,
        "run_names": run_names,
        "errors": errors,
        "warnings": warnings,
    }


def compare_generated_to_reference(reference_dir: str | Path, generated_dir: str | Path) -> dict[str, Any]:
    reference = Path(reference_dir).expanduser().resolve()
    generated = Path(generated_dir).expanduser().resolve()
    reference_headers = inspect_hms_component_headers(reference)
    generated_headers = inspect_hms_component_headers(generated)
    reference_types = sorted({row["header_type"] for row in reference_headers})
    generated_types = sorted({row["header_type"] for row in generated_headers})
    reference_validation = validate_hms_component_syntax(reference)
    generated_validation = validate_hms_component_syntax(generated)
    differences = []
    for component_type in ("Project", "Basin", "Meteorology", "Control", "Run"):
        differences.append(
            {
                "component_type": component_type,
                "reference_present": component_type in reference_types,
                "generated_present": component_type in generated_types,
                "match": component_type in reference_types and component_type in generated_types,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_dir": str(reference),
        "generated_dir": str(generated),
        "status": "passed" if generated_validation["status"] == "passed" else "failed",
        "reference_headers": reference_headers,
        "generated_headers": generated_headers,
        "reference_references": inspect_hms_component_references(reference),
        "generated_references": inspect_hms_component_references(generated),
        "component_comparison": differences,
        "reference_validation": reference_validation,
        "generated_validation": generated_validation,
        "calibration_findings": [
            "HEC-HMS component files are stored in the project root and referenced with Filename/FileName.",
            "The project file registers Basin, Precipitation, and Control components; simulation runs are stored in the sibling .run file.",
            "Every component block ends with End:, and component headers carry names used by run references.",
            "Version 4.13, date/time fields, file path separator, and unit system follow component-specific conventions.",
        ],
    }


def write_hms_format_comparison_report(output_dir: str | Path, comparison: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "hms_reference_format.json"
    xlsx_path = output / "hms_reference_format.xlsx"
    md_path = output / "hms_format_comparison.md"
    json_path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with pd.ExcelWriter(xlsx_path) as writer:
        pd.DataFrame(comparison.get("component_comparison", [])).to_excel(writer, sheet_name="component_comparison", index=False)
        pd.DataFrame(comparison.get("reference_headers", [])).to_excel(writer, sheet_name="reference_headers", index=False)
        pd.DataFrame(comparison.get("generated_headers", [])).to_excel(writer, sheet_name="generated_headers", index=False)
        pd.DataFrame(comparison.get("reference_references", [])).to_excel(writer, sheet_name="reference_refs", index=False)
        pd.DataFrame(comparison.get("generated_references", [])).to_excel(writer, sheet_name="generated_refs", index=False)
    lines = [
        "# HEC-HMS File Format Comparison",
        "",
        f"- Status: `{comparison.get('status', 'unknown')}`",
        f"- Reference: `{comparison.get('reference_dir', '')}`",
        f"- Generated: `{comparison.get('generated_dir', '')}`",
        f"- Reference syntax: `{comparison.get('reference_validation', {}).get('status', 'unknown')}`",
        f"- Generated syntax: `{comparison.get('generated_validation', {}).get('status', 'unknown')}`",
        "",
        "## Calibration Findings",
        "",
    ]
    lines.extend(f"- {finding}" for finding in comparison.get("calibration_findings", []))
    lines.extend(["", "## Generated Errors", ""])
    lines.extend(f"- {error}" for error in comparison.get("generated_validation", {}).get("errors", []))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "xlsx": xlsx_path, "markdown": md_path}


def discover_reference_precipitation_components(reference_project_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(reference_project_dir).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        suffix = path.suffix.lower()
        if suffix not in {".gage", ".met", ".run", ".control", ".hms", ".dss"}:
            continue
        text = "" if suffix == ".dss" else path.read_text(encoding="utf-8", errors="replace")
        relevant = suffix in {".gage", ".met", ".dss"} or any(
            token in text for token in ("Precip", "Gage", "DSS File")
        )
        if relevant:
            rows.append(
                {
                    "file": str(path),
                    "relative_path": str(path.relative_to(root)),
                    "suffix": suffix,
                    "size_bytes": path.stat().st_size,
                    "evidence": "direct_file" if suffix in {".gage", ".met"} else "referenced_or_related",
                }
            )
    return rows


def discover_reference_time_series_files(reference_project_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(reference_project_dir).expanduser().resolve()
    referenced: set[str] = set()
    for gage_file in root.glob("*.gage"):
        parsed = _parse_component(gage_file, "Gage Manager")
        for block in parsed["blocks"]:
            for value in block["property_map"].get("Filename", []):
                referenced.add(value)
    rows = []
    for path in sorted(root.rglob("*.dss")):
        relative = str(path.relative_to(root))
        rows.append(
            {
                "file": str(path),
                "relative_path": relative,
                "size_bytes": path.stat().st_size,
                "referenced_by_gage": relative in referenced or path.name in referenced,
            }
        )
    return rows


def inspect_reference_precipitation_gages(reference_project_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(reference_project_dir).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.gage")):
        parsed = _parse_component(path, "Gage Manager")
        for block in parsed["blocks"]:
            props = block["property_map"]
            if block["block_type"] != "Gage" or props.get("Gage Type", [""])[0] != "Precipitation":
                continue
            pathname = props.get("Pathname", [""])[0]
            pathname_parts = pathname.strip("/").split("/") + [""] * 6
            rows.append(
                {
                    "file": str(path),
                    "gage_name": block["name"],
                    "gage_type": props.get("Gage Type", [""])[0],
                    "data_source_type": props.get("Data Source Type", [""])[0],
                    "dss_file": props.get("Filename", [""])[0],
                    "pathname": pathname,
                    "data_type": pathname_parts[2],
                    "interval": pathname_parts[4],
                    "start": props.get("Start Time", [""])[0],
                    "end": props.get("End Time", [""])[0],
                    "units_observed": props.get("Units", [""])[0],
                    "units_inferred": "IN for English-unit meteorology; not explicit in the gage block",
                }
            )
    return rows


def _pathname_parts(pathname: str) -> dict[str, str]:
    parts = pathname.strip("/").split("/")
    parts += [""] * (6 - len(parts))
    return dict(zip(("a_part", "b_part", "c_part", "d_part", "e_part", "f_part"), parts[:6]))


def inspect_reference_dss_pathnames(reference_project_dir: str | Path) -> list[dict[str, Any]]:
    from hydrolite.hec_hms_precipitation import catalog_dss_file

    rows: list[dict[str, Any]] = []
    for item in discover_reference_time_series_files(reference_project_dir):
        catalog = catalog_dss_file(item["file"])
        for pathname in catalog.get("pathnames", []):
            rows.append(
                {
                    "dss_file": item["file"],
                    "pathname": pathname,
                    **_pathname_parts(pathname),
                    "catalog_status": catalog.get("status"),
                }
            )
    return rows


def inspect_reference_meteorologic_precipitation(reference_project_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(reference_project_dir).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.met")):
        parsed = parse_hms_meteorologic_file(path)
        header = parsed["blocks"][0] if parsed["blocks"] else {"property_map": {}, "name": ""}
        method = header["property_map"].get("Precipitation Method", [""])[0]
        recording_gages = [
            block["name"]
            for block in parsed["blocks"]
            if block["block_type"] == "Gage" and block["property_map"].get("Type", [""])[0] == "Recording"
        ]
        subbasin_blocks = [block for block in parsed["blocks"] if block["block_type"] == "Subbasin"]
        for block in subbasin_blocks:
            props = block["property_map"]
            rows.append(
                {
                    "file": str(path),
                    "meteorologic_model": header.get("name", ""),
                    "precipitation_method": method,
                    "subbasin": block["name"],
                    "recording_gages": ", ".join(recording_gages),
                    "assigned_gages": ", ".join(props.get("Gage", [])),
                    "volume_weights": ", ".join(props.get("Volume Weight", [])),
                    "temporal_distribution_weights": ", ".join(props.get("Temporal Distribution Weight", [])),
                }
            )
        if not any(row["file"] == str(path) for row in rows):
            rows.append(
                {
                    "file": str(path),
                    "meteorologic_model": header.get("name", ""),
                    "precipitation_method": method,
                    "subbasin": "",
                    "recording_gages": "",
                    "assigned_gages": "",
                    "volume_weights": "",
                    "temporal_distribution_weights": "",
                }
            )
    return rows


def compare_precipitation_configuration(
    reference_project_dir: str | Path, generated_project_dir: str | Path
) -> dict[str, Any]:
    reference_gages = inspect_reference_precipitation_gages(reference_project_dir)
    generated_gages = inspect_reference_precipitation_gages(generated_project_dir)
    reference_met = inspect_reference_meteorologic_precipitation(reference_project_dir)
    generated_met = inspect_reference_meteorologic_precipitation(generated_project_dir)
    return {
        "reference_project": str(Path(reference_project_dir).resolve()),
        "generated_project": str(Path(generated_project_dir).resolve()),
        "reference_gages": reference_gages,
        "generated_gages": generated_gages,
        "reference_meteorology": reference_met,
        "generated_meteorology": generated_met,
        "checks": {
            "reference_has_external_dss_gage": any(row["data_source_type"] == "External DSS" for row in reference_gages),
            "generated_has_external_dss_gage": any(row["data_source_type"] == "External DSS" for row in generated_gages),
            "reference_uses_weighted_gages": any(row["precipitation_method"] == "Weighted Gages" for row in reference_met),
            "generated_uses_weighted_gages": any(row["precipitation_method"] == "Weighted Gages" for row in generated_met),
        },
    }


def write_precipitation_reference_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "precipitation_reference.json"
    catalog_path = output / "dss_pathname_catalog.json"
    xlsx_path = output / "precipitation_reference_summary.xlsx"
    md_path = output / "precipitation_reference_report.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    catalog_path.write_text(json.dumps(result.get("dss_pathnames", []), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with pd.ExcelWriter(xlsx_path) as writer:
        pd.DataFrame(result.get("components", [])).to_excel(writer, sheet_name="components", index=False)
        pd.DataFrame(result.get("gages", [])).to_excel(writer, sheet_name="precipitation_gages", index=False)
        pd.DataFrame(result.get("meteorology", [])).to_excel(writer, sheet_name="meteorology", index=False)
        pd.DataFrame(result.get("dss_pathnames", [])).to_excel(writer, sheet_name="dss_pathnames", index=False)
        pd.DataFrame(result.get("time_series_files", [])).to_excel(writer, sheet_name="time_series_files", index=False)
        pd.DataFrame(result.get("run_references", [])).to_excel(writer, sheet_name="run_references", index=False)
        pd.DataFrame(result.get("control_windows", [])).to_excel(writer, sheet_name="control_windows", index=False)
    lines = [
        "# HEC-HMS Precipitation Reference",
        "",
        f"- Reference project: `{result.get('reference_project', '')}`",
        f"- Precipitation gages: `{len(result.get('gages', []))}`",
        f"- DSS pathnames cataloged: `{len(result.get('dss_pathnames', []))}`",
        "",
        "## Directly Observed",
        "",
    ]
    lines.extend(f"- {item}" for item in result.get("direct_observations", []))
    lines.extend(["", "## Inferred From References", ""])
    lines.extend(f"- {item}" for item in result.get("inferences", []))
    lines.extend(["", "## Not Yet Confirmed", ""])
    lines.extend(f"- {item}" for item in result.get("unconfirmed", []))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"markdown": md_path, "json": json_path, "xlsx": xlsx_path, "catalog": catalog_path}
