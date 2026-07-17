from __future__ import annotations

import hashlib
from pathlib import Path
import shutil

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]


def _hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _reference(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "reference.hms").write_text(
        "Project: reference\n     Version: 4.13\nEnd:\n\n"
        "Precipitation: met\n     Filename: met.met\nEnd:\n\n"
        "Basin: basin\n     Filename: basin.basin\nEnd:\n\n"
        "Control: control\n     FileName: control.control\nEnd:\n",
        encoding="utf-8",
    )
    (root / "basin.basin").write_text("Basin: basin\n     Version: 4.13\nEnd:\n", encoding="utf-8")
    (root / "met.met").write_text("Meteorology: met\n     Version: 4.13\nEnd:\n", encoding="utf-8")
    (root / "control.control").write_text("Control: control\n     Version: 4.13\nEnd:\n", encoding="utf-8")
    (root / "reference.run").write_text(
        "Run: Short Run\n     Basin: basin\n     Precip: met\n     Control: control\nEnd:\n",
        encoding="utf-8",
    )
    return root


def _hydrolite_project(root: Path) -> Path:
    (root / "cases").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "reports").mkdir()
    (root / "output").mkdir()
    (root / "project.yaml").write_text(
        yaml.safe_dump({"project_name": "HMS fixture", "paths": {"cases_dir": "cases", "data_dir": "data"}}),
        encoding="utf-8",
    )
    (root / "cases" / "demo.yaml").write_text("case_name: demo\n", encoding="utf-8")
    shutil.copy2(ROOT / "templates/data/examples/subbasins_example.csv", root / "data/subbasins.csv")
    shutil.copy2(ROOT / "templates/data/examples/reaches_example.csv", root / "data/reaches.csv")
    shutil.copy2(ROOT / "templates/data/examples/rainfall_example.csv", root / "data/rainfall.csv")
    return root


def test_reference_inspection_scripts_and_unavailable_probe(monkeypatch, tmp_path: Path):
    import hydrolite.hec_hms as hms

    reference = _reference(tmp_path / "reference")
    inspected = hms.inspect_hms_reference_project(reference)
    assert inspected["complete_components"]
    assert inspected["run_names"] == ["Short Run"]
    assert hms.discover_hms_run_names(reference) == ["Short Run"]
    open_script = hms.build_hms_open_script(reference, tmp_path / "open.py")
    compute_script = hms.build_official_hms_compute_script(reference, "Short Run", tmp_path / "compute.py")
    legacy_script = hms.build_legacy_hms_compute_script(reference, "Short Run", tmp_path / "legacy.py")
    assert "Project.open" in open_script.read_text(encoding="utf-8")
    assert "project.computeRun" in compute_script.read_text(encoding="utf-8")
    assert "JythonHms" in legacy_script.read_text(encoding="utf-8")
    monkeypatch.setattr(hms, "_first_hec_hms_executable", lambda: None)
    result = hms.run_official_hms_reference(reference, execute=True, timeout=2)
    assert result["open_status"] == "open_failed"
    assert result["compute_status"] == "skipped_open_failed"
    assert Path(result["report_files"]["markdown"]).exists()


def test_calibrated_project_compute_gates_and_dss_discovery(monkeypatch, tmp_path: Path):
    import hydrolite.hec_hms as hms

    before = _hashes(ROOT / "data_raw")
    source = _hydrolite_project(tmp_path / "source")
    reference = _reference(tmp_path / "reference")
    generated = tmp_path / "verified"
    result = hms.create_calibrated_hms_project_from_hydrolite(source, generated, reference)
    assert result["status"] == "passed"
    for name in (
        "HydroLite_HMS_Project.hms",
        "hydrolite_basin.basin",
        "hydrolite_meteorologic.met",
        "hydrolite_control.control",
        "hydrolite_run.run",
        "HydroLite_HMS_Project.run",
        "scripts/open_generated_project.py",
        "scripts/compute_generated_project.py",
        "reports/hec_hms_format_validation.md",
        "reports/hec_hms_format_validation.json",
        "reports/hec_hms_reference_comparison.xlsx",
    ):
        assert (generated / name).exists()
    monkeypatch.setattr(hms, "_first_hec_hms_executable", lambda: None)
    opened = hms.run_hms_open_probe(generated, timeout=2)
    assert opened["status"] == "open_failed"
    computed = hms.run_hms_compute_probe(generated, timeout=2, execute=True)
    assert computed["status"] == "skipped_gate_failed"
    assert computed["readiness"]["rainfall_ready"] is False
    dss_outputs = hms.write_hms_dss_discovery_report(generated)
    assert all(path.exists() for path in dss_outputs.values())
    assert _hashes(ROOT / "data_raw") == before


def test_hms_official_cli_routes_and_ui(monkeypatch, tmp_path: Path):
    import hydrolite.__main__ as cli
    import hydrolite.ui.pages.hec_hms as page

    reference = _reference(tmp_path / "reference")
    generated = _reference(tmp_path / "generated")
    assert cli.main(["hms", "compare-format", str(reference), str(generated)]) == 0
    monkeypatch.setattr(cli, "run_hms_open_probe", lambda path: {"status": "unavailable", "project_dir": str(path)})
    assert cli.main(["hms", "open-probe", str(generated)]) == 0
    assert cli.main(["hms", "discover-dss", str(generated)]) == 0
    assert callable(page.render)


def test_official_precipitation_structure_inspection(monkeypatch, tmp_path: Path):
    import hydrolite.hec_hms_precipitation as precipitation
    from hydrolite.hec_hms_format import (
        discover_reference_precipitation_components,
        discover_reference_time_series_files,
        inspect_reference_dss_pathnames,
        inspect_reference_meteorologic_precipitation,
        inspect_reference_precipitation_gages,
        write_precipitation_reference_report,
    )

    reference = _reference(tmp_path / "precip_reference")
    (reference / "reference.gage").write_text(
        "Gage Manager: reference\nEnd:\n\nGage: Rain\n     Gage Type: Precipitation\n"
        "     Data Source Type: External DSS\n     Filename: rain.dss\n"
        "     Pathname: /P/RAIN/PRECIP-INC//1HOUR/OBS/\nEnd:\n",
        encoding="utf-8",
    )
    (reference / "met.met").write_text(
        "Meteorology: met\n     Precipitation Method: Weighted Gages\nEnd:\n\n"
        "Precip Method Parameters: S1\n     Recording Gage: Rain\n     Recording Gage Weight: 1\nEnd:\n",
        encoding="utf-8",
    )
    (reference / "rain.dss").write_bytes(b"fixture")
    monkeypatch.setattr(
        precipitation,
        "catalog_dss_file",
        lambda *_: {"status": "success", "pathnames": ["/P/RAIN/PRECIP-INC/01JUN2026/1HOUR/OBS/"]},
    )
    assert discover_reference_precipitation_components(reference)
    assert discover_reference_time_series_files(reference)[0]["referenced_by_gage"] is True
    assert inspect_reference_precipitation_gages(reference)[0]["gage_name"] == "Rain"
    assert inspect_reference_meteorologic_precipitation(reference)[0]["precipitation_method"] == "Weighted Gages"
    assert inspect_reference_dss_pathnames(reference)[0]["c_part"] == "PRECIP-INC"
    result = {
        "reference_project": str(reference),
        "components": discover_reference_precipitation_components(reference),
        "time_series_files": discover_reference_time_series_files(reference),
        "gages": inspect_reference_precipitation_gages(reference),
        "meteorology": inspect_reference_meteorologic_precipitation(reference),
        "dss_pathnames": inspect_reference_dss_pathnames(reference),
        "direct_observations": ["observed"],
        "inferences": ["inferred"],
        "unconfirmed": ["unconfirmed"],
    }
    outputs = write_precipitation_reference_report(tmp_path / "reports", result)
    assert all(path.exists() for path in outputs.values())


def test_official_samples_and_sensitive_artifacts_are_not_tracked():
    import subprocess

    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=False).stdout.splitlines()
    assert not any(path.endswith((".hms", ".basin", ".met", ".control", ".run", ".dss")) for path in tracked)
    assert not any(path.startswith("external/") for path in tracked)
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
