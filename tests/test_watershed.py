from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SWMM_INP = ROOT / "data_raw" / "swmm" / "demo.inp"
PROTECTED_TAGS = {
    "v0.5.0-alpha.2": "e81f194cbca58c3a88f8176b6da114d6a46ee1c6",
    "v0.6.0-beta": "67a386dd0de53ef7c22bdbd054adaf7c5aef122b",
    "v0.6.0-beta.1": "616fa6754b73b64d222ad508c1ab57bb52364365",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "hydrolite", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )


def test_watershed_module_and_backend_detection():
    import hydrolite.watershed as watershed

    assert callable(watershed.run_watershed_mvp)
    candidates = watershed.list_watershed_algorithm_candidates()
    assert candidates
    assert {"grass", "saga", "watershed", "fill_sinks", "flow_accumulation", "taudem", "whitebox"} <= {
        row["category"] for row in candidates
    }
    diagnosis = watershed.detect_watershed_backends()
    assert diagnosis["status"] in {"available", "partial", "fallback", "unavailable"}
    assert diagnosis["grass_diagnosis"]["status"] in {"available", "unavailable"}
    assert diagnosis["capabilities"]["flow_accumulation"]
    assert diagnosis["capabilities"]["stream_network"]


def test_demo_dem_inspection_and_mvp_outputs(tmp_path: Path):
    from hydrolite.watershed import create_demo_dem, inspect_dem, run_watershed_mvp, validate_watershed_outputs

    dem = create_demo_dem(tmp_path / "demo_dem.asc")
    assert dem.exists()
    inspection = inspect_dem(dem)
    assert inspection["exists"]
    assert inspection["ncols"] == 12
    assert inspection["nrows"] == 12
    result = run_watershed_mvp(dem, tmp_path / "watershed")
    assert result["status"] in {"available", "partial", "fallback"}
    assert result["steps"]["flow_accumulation"]["status"] == "success"
    assert result["steps"]["stream_network"]["status"] == "success"
    validation = validate_watershed_outputs(tmp_path / "watershed")
    assert validation["status"] == "passed"
    assert validation["data_template_validation"]["subbasins"]["status"] == "passed"
    assert validation["data_template_validation"]["reaches"]["status"] == "passed"


def test_write_watershed_report(tmp_path: Path):
    from hydrolite.watershed import write_watershed_report

    report = write_watershed_report(
        tmp_path,
        {
            "status": "fallback",
            "dem": str(tmp_path / "demo.asc"),
            "backends": {},
            "dem_inspection": {},
            "steps": {},
            "outputs": {},
            "validation": {"status": "warning"},
        },
    )
    assert report.exists()
    assert "MVP" in report.read_text(encoding="utf-8")


def test_watershed_cli_commands(tmp_path: Path):
    output = tmp_path / "cli_watershed"
    dem = output / "demo_dem.asc"
    commands = [
        ("watershed", "backends"),
        ("watershed", "create-demo-dem", str(dem)),
        ("watershed", "inspect", str(dem)),
    ]
    for command in commands:
        result = _run(*command)
        assert result.returncode == 0, result.stdout + result.stderr

    from hydrolite.watershed import run_watershed_mvp

    run_watershed_mvp(dem, output)
    for command in (("watershed", "validate", str(output)), ("watershed", "report", str(output))):
        result = _run(*command)
        assert result.returncode == 0, result.stdout + result.stderr


def test_watershed_streamlit_and_workflow_stage_imports():
    import hydrolite.ui.pages.watershed_delineation as watershed_page
    from hydrolite.workflow_engine import get_workflow_stage

    assert callable(watershed_page.render)
    stage = get_workflow_stage("watershed_delineation")
    assert stage["status"] == "partial"
    assert stage["cli_command"] == "python -m hydrolite watershed mvp"
    assert "watershed_report.md" in stage["expected_outputs"]


def test_watershed_does_not_modify_data_raw_or_tags():
    before = _sha256(SWMM_INP)
    result = _run("watershed", "backends")
    assert result.returncode == 0
    assert _sha256(SWMM_INP) == before
    for tag, expected in PROTECTED_TAGS.items():
        completed = subprocess.run(["git", "rev-parse", tag], cwd=ROOT, text=True, capture_output=True, check=False)
        assert completed.returncode == 0
        assert completed.stdout.strip() == expected


def test_no_tracked_secrets_external_or_model_weights():
    completed = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=False)
    tracked = completed.stdout.splitlines()
    assert not any(path.startswith("external/") for path in tracked)
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
