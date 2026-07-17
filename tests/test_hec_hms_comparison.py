from __future__ import annotations

from pathlib import Path
import zipfile

import pandas as pd

from hydrolite.hec_hms_results import _portable_path, align_flow_timeseries, export_hms_comparison_bundle, validate_flow_alignment


def _series(start: str, values: list[float], frequency: str = "1h") -> pd.DataFrame:
    return pd.DataFrame({"timestamp": pd.date_range(start, periods=len(values), freq=frequency), "flow_cms": values})


def test_exact_alignment_reports_unmatched_records():
    hms = _series("2026-06-01", [0, 2, 4])
    hydro = _series("2026-06-01", [0, 1, 2, 1])
    result = align_flow_timeseries(hms, hydro)
    assert result["method"] == "exact"
    assert result["aligned_records"] == 3
    assert result["unmatched_hms"] == 0
    assert result["unmatched_hydrolite"] == 1
    assert validate_flow_alignment(result)["status"] == "passed"


def test_interval_mismatch_requires_explicit_method():
    hms = _series("2026-06-01", [0, 2, 4], "1h")
    hydro = _series("2026-06-01", [0, 1, 2, 3, 4], "30min")
    exact = align_flow_timeseries(hms, hydro)
    assert exact["aligned_records"] == 3
    resampled = align_flow_timeseries(hms, hydro, method="resample_mean")
    assert "no interpolation" in " ".join(resampled["warnings"])


def test_hydrolite_discovery_prefers_requested_project(tmp_path: Path, monkeypatch):
    import hydrolite.hec_hms_results as results

    project = tmp_path / "project"
    local = project / "output" / "case" / "result_flow.csv"
    global_file = tmp_path / "output" / "demo" / "result_flow.csv"
    local.parent.mkdir(parents=True)
    global_file.parent.mkdir(parents=True)
    content = "time,outflow_cms\n2026-06-01 00:00,1\n2026-06-01 01:00,2\n"
    local.write_text(content, encoding="utf-8")
    global_file.write_text(content, encoding="utf-8")
    monkeypatch.setattr(results, "PROJECT_ROOT", tmp_path)
    discovered = results.discover_hydrolite_flow_outputs(project)
    assert Path(discovered["selected"]["path"]).is_relative_to(project)


def test_safe_comparison_bundle_excludes_forbidden_files(tmp_path: Path):
    (tmp_path / "comparison_report.md").write_text("report", encoding="utf-8")
    (tmp_path / "aligned_outlet_timeseries.csv").write_text("timestamp,flow\n", encoding="utf-8")
    (tmp_path / "model.dss").write_text("forbidden", encoding="utf-8")
    (tmp_path / "secret.csv").write_text("forbidden", encoding="utf-8")
    bundle = export_hms_comparison_bundle(tmp_path)
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
    assert "comparison_report.md" in names
    assert "aligned_outlet_timeseries.csv" in names
    assert not any(".dss" in name or "secret" in name for name in names)


def test_portable_path_removes_private_parent_directories(tmp_path: Path):
    rendered = _portable_path(tmp_path / "private" / "project")
    assert str(tmp_path) not in rendered


def test_ui_page_and_docs_import():
    import hydrolite.ui.pages.hec_hms as page

    assert callable(page.render)
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs" / "hec_hms_dss_flow_results.md").is_file()
    assert (root / "docs" / "hec_hms_hydrolite_comparison.md").is_file()


def test_hms_result_cli_routes(monkeypatch, tmp_path: Path):
    import hydrolite.__main__ as cli

    catalog = {"status": "success", "pathname_count": 2, "flow_pathname_count": 1, "flow_pathnames": ["//Outlet/FLOW//1Hour/RUN:r/"], "classified": []}
    read = {"status": "success", "backend": "test", "requested_pathname_count": 1, "successful_pathname_count": 1, "failed_pathname_count": 0, "runtime_seconds": 0.1, "series": []}
    extraction = {"status": "completed", "pathname_count": 2, "flow_pathname_count": 1, "read_result": read, "outlet_selection": {"outlet_selection_status": "verified"}}
    monkeypatch.setattr(cli, "load_hms_result_catalog", lambda *_: catalog)
    monkeypatch.setattr(cli, "read_hms_dss_timeseries", lambda *_args, **_kwargs: read.copy())
    monkeypatch.setattr(cli, "write_hms_timeseries_catalog", lambda *_: {})
    monkeypatch.setattr(cli, "run_hms_result_extraction", lambda *_: extraction)
    monkeypatch.setattr(cli, "map_hms_results_to_hydrolite_elements", lambda *_: {"status": "passed", "mapped_count": 1, "unmapped_count": 0})
    monkeypatch.setattr(cli, "select_verified_outlet_series", lambda *_: {"outlet_selection_status": "verified", "candidates": [], "selected_outlet": "Outlet", "selected_pathname": "//Outlet/FLOW//1Hour/RUN:r/"})
    monkeypatch.setattr(cli, "write_outlet_selection_report", lambda *_: {"json": tmp_path / "outlet.json"})
    monkeypatch.setattr(cli, "run_hms_hydrolite_comparison", lambda *_: {"status": "completed", "outlet_selection": {"selected_outlet": "Outlet"}, "alignment": {}, "comparison_metrics": {}, "event_differences": {}})
    monkeypatch.setattr(cli, "validate_hms_comparison_outputs", lambda *_: {"status": "passed", "errors": []})
    assert cli.main(["hms", "catalog-results", "hms"]) == 0
    assert cli.main(["hms", "read-flow-results", "hms"]) == 0
    assert cli.main(["hms", "identify-outlet", "hms", "hydro"]) == 0
    assert cli.main(["hms", "extract-results", "hms"]) == 0
    assert cli.main(["hms", "compare-hydrolite", "hms", "hydro"]) == 0
    assert cli.main(["hms", "validate-comparison", str(tmp_path)]) == 0
