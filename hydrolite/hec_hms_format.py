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
    "Precip Method Parameters",
}


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
