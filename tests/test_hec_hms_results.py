from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import hydrolite.hec_hms_results as results


def test_pathname_six_parts_and_flow_classification():
    parsed = results.parse_dss_pathname("//Outlet/FLOW//1Hour/RUN:run/")
    assert [parsed[f"{part}_part"] for part in "abcdef"] == ["", "Outlet", "FLOW", "", "1Hour", "RUN:run"]
    assert parsed["flow_semantics"] == "instantaneous_flow"
    assert results.classify_hms_result_pathname("//S1/FLOW-CUMULATIVE//1Hour/RUN:run/")["flow_semantics"] == "cumulative_volume"
    assert results.classify_hms_result_pathname("//S1/FLOW-UNIT GRAPH/TS-PATTERN/1Hour/RUN:run/")["flow_semantics"] == "response_pattern"


def test_catalog_flow_identification_and_read_script(tmp_path: Path):
    catalog = {"pathnames": ["//Outlet/FLOW//1Hour/RUN:run/", "//S1/PRECIP-INC//1Hour/RUN:run/"]}
    assert results.find_hms_flow_pathnames(catalog) == [catalog["pathnames"][0]]
    script = results.build_hms_dss_read_script(tmp_path / "model.dss", catalog["pathnames"][:1], tmp_path)
    text = script.read_text(encoding="ascii")
    assert "HecDss.open" in text
    assert "HYDROLITE_HMS_TS_META" in text


def test_dss_read_preserves_missing_values(monkeypatch, tmp_path: Path):
    pathname = "//Outlet/FLOW//1Hour/RUN:run/"
    monkeypatch.setattr(results, "load_hms_result_catalog", lambda _path: {"flow_pathnames": [pathname]})
    stdout = "\n".join(
        [
            f"HYDROLITE_HMS_TS_META|0|{pathname}|3|1 June 2026, 00:00|1 June 2026, 02:00|60|M3/S|INST-VAL|1",
            "HYDROLITE_HMS_TS_VALUES|0|0.0,,2.0",
        ]
    )
    monkeypatch.setattr(results, "_run_hms_script", lambda *_args, **_kwargs: {"stdout": stdout, "stderr": "", "returncode": 0, "runtime_seconds": 0.1, "process_terminated": True})
    result = results.read_hms_dss_timeseries(tmp_path / "model.dss", [pathname], tmp_path / "out")
    assert result["status"] == "success"
    frame = pd.read_csv(result["series"][0]["csv_path"])
    assert pd.isna(frame.loc[1, "flow_original"])
    assert frame.loc[2, "flow_original"] == 2.0


def test_cfs_and_unknown_unit_conversion():
    converted, status = results.convert_flow_values([1.0], "CFS", "CMS")
    assert converted.iloc[0] == pytest.approx(0.028316846592)
    assert status["status"] == "passed"
    unresolved, status = results.convert_flow_values([1.0], "unknown", "CMS")
    assert unresolved.isna().all()
    assert status["status"] == "unit_unresolved"


def test_result_window_crosscheck_uses_project_context(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "hec_hms_rainfall_context.json").write_text(
        '{"start":"2026-06-01T00:00:00","end":"2026-06-01T02:00:00"}', encoding="utf-8"
    )
    result = {
        "series": [
            {
                "read_status": "success",
                "flow_semantics": "instantaneous_flow",
                "start": "1 June 2026, 00:00",
                "end": "1 June 2026, 02:00",
            }
        ]
    }
    assert results._cross_validate_result_window(tmp_path, result)["status"] == "passed"


def test_outlet_selection_is_topology_based_not_peak(tmp_path: Path):
    (tmp_path / "demo.basin").write_text(
        "Basin: demo\nEnd:\n\nReach: R1\n     Downstream: Outlet\nEnd:\n\nJunction: Outlet\nEnd:\n",
        encoding="utf-8",
    )
    pathnames = ["//R1/FLOW//1Hour/RUN:run/", "//Outlet/FLOW//1Hour/RUN:run/"]
    series = []
    for pathname, peak in zip(pathnames, (999.0, 2.0)):
        item = results.parse_dss_pathname(pathname)
        item.update({"read_status": "success", "values": [0.0, peak], "csv_path": "unused"})
        series.append(item)
    selected = results.select_verified_outlet_series(tmp_path, {"requested_pathnames": pathnames, "series": series}, {"rows": []})
    assert selected["selected_outlet"] == "Outlet"
    assert selected["selected_pathname"] == pathnames[1]
    assert selected["outlet_selection_status"] == "verified"


def test_multiple_outlets_block_selection(tmp_path: Path):
    (tmp_path / "demo.basin").write_text(
        "Basin: demo\nEnd:\n\nJunction: OutletA\nEnd:\n\nJunction: OutletB\nEnd:\n",
        encoding="utf-8",
    )
    pathnames = ["//OutletA/FLOW//1Hour/RUN:run/", "//OutletB/FLOW//1Hour/RUN:run/"]
    catalog = {"classified": [results.parse_dss_pathname(path) for path in pathnames]}
    candidates = results.identify_hms_outlet_candidates(tmp_path, {"rows": []}, catalog)
    assert candidates["status"] == "multiple_outlets"
