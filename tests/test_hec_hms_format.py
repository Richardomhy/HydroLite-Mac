from __future__ import annotations

from pathlib import Path


def _component_project(root: Path, name: str = "fixture") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.hms").write_text(
        "\n".join(
            [
                f"Project: {name}",
                "     Version: 4.13",
                "     Description: Test project",
                "     Preserved Unknown Line",
                "End:",
                "",
                "Precipitation: met",
                "     Filename: met.met",
                "End:",
                "",
                "Basin: basin",
                "     Filename: basin.basin",
                "End:",
                "",
                "Control: control",
                "     FileName: control.control",
                "End:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "basin.basin").write_text(
        "Basin: basin\n     Version: 4.13\n     Unit System: Metric\nEnd:\n\nJunction: Outlet\nEnd:\n",
        encoding="utf-8",
    )
    (root / "met.met").write_text(
        "Meteorology: met\n     Version: 4.13\n     Precipitation Method: None\nEnd:\n",
        encoding="utf-8",
    )
    (root / "control.control").write_text(
        "Control: control\n     Version: 4.13\n     Start Date: 1 January 2026\n     Start Time: 00:00\n"
        "     End Date: 1 January 2026\n     End Time: 12:00\n     Time Interval: 60\nEnd:\n",
        encoding="utf-8",
    )
    (root / f"{name}.run").write_text(
        "Run: run\n     Basin: basin\n     Precip: met\n     Control: control\nEnd:\n",
        encoding="utf-8",
    )
    return root


def test_hms_format_parsers_preserve_unknown_lines(tmp_path: Path):
    from hydrolite.hec_hms_format import (
        parse_hms_basin_file,
        parse_hms_control_file,
        parse_hms_meteorologic_file,
        parse_hms_project_file,
        parse_hms_run_file,
    )

    root = _component_project(tmp_path / "project")
    project = parse_hms_project_file(root / "fixture.hms")
    assert project["header"] == {"block_type": "Project", "name": "fixture"}
    assert any("Preserved Unknown Line" in row["text"] for row in project["unknown_lines"])
    assert project["raw_sections"]
    assert parse_hms_basin_file(root / "basin.basin")["header"]["block_type"] == "Basin"
    assert parse_hms_meteorologic_file(root / "met.met")["header"]["block_type"] == "Meteorology"
    assert parse_hms_control_file(root / "control.control")["header"]["block_type"] == "Control"
    assert parse_hms_run_file(root / "fixture.run")["header"]["block_type"] == "Run"


def test_hms_format_comparison_and_reports(tmp_path: Path):
    from hydrolite.hec_hms_format import (
        compare_generated_to_reference,
        inspect_hms_component_headers,
        inspect_hms_component_references,
        validate_hms_component_syntax,
        write_hms_format_comparison_report,
    )

    reference = _component_project(tmp_path / "reference", "reference")
    generated = _component_project(tmp_path / "generated", "generated")
    assert inspect_hms_component_headers(reference)
    assert inspect_hms_component_references(reference)
    assert validate_hms_component_syntax(generated)["status"] == "passed"
    comparison = compare_generated_to_reference(reference, generated)
    assert comparison["status"] == "passed"
    outputs = write_hms_format_comparison_report(tmp_path / "reports", comparison)
    assert all(path.exists() for path in outputs.values())
