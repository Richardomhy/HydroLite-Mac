from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]


def _event_rows(
    provenance_statuses: list[str],
    *,
    simulation_provenance_status: str = "confirmed_hydrolite_run",
) -> pd.DataFrame:
    starts = pd.date_range("2026-01-01", periods=len(provenance_statuses), freq="7D")
    return pd.DataFrame(
        {
            "event_id": [f"event_{index + 1}" for index in range(len(starts))],
            "event_start": starts,
            "event_end": starts + pd.Timedelta(hours=6),
            "split_role": ["calibration", "validation"][: len(starts)],
            "provenance_status": provenance_statuses,
            "simulation_provenance_status": simulation_provenance_status,
            "hydrolite_run_id": [f"run_{index + 1}" for index in range(len(starts))],
        }
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            _sha256(path),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_single_unconfirmed_event_cannot_be_independent_validation():
    from hydrolite.real_project_model import assess_event_gate

    gate = assess_event_gate(_event_rows(["requires_confirmation"]))

    assert gate["event_count"] == 1
    assert gate["confirmed_event_count"] == 0
    assert gate["independent_validation_ready"] is False
    assert gate["hydrolite_model_validated"] is False
    assert gate["scientific_status"] == "real_data_diagnostic"
    assert "insufficient_independent_events" in gate["blockers"]
    assert "unconfirmed_event_provenance" in gate["blockers"]


def test_two_events_with_one_unconfirmed_still_cannot_be_independent_validation():
    from hydrolite.real_project_model import assess_event_gate

    gate = assess_event_gate(_event_rows(["confirmed", "requires_confirmation"]))

    assert gate["event_count"] == 2
    assert gate["confirmed_event_count"] == 1
    assert gate["independent_validation_ready"] is False
    assert gate["hydrolite_model_validated"] is False
    assert "unconfirmed_event_provenance" in gate["blockers"]


def test_confirmed_complete_events_with_hydrolite_runs_can_pass_gate():
    from hydrolite.real_project_model import assess_event_gate

    gate = assess_event_gate(_event_rows(["confirmed", "confirmed"]))

    assert gate["independent_validation_ready"] is True
    assert gate["hydrolite_model_validated"] is True
    assert gate["scientific_status"] == "real_data_tested"


def test_unknown_existing_simulation_cannot_be_attributed_to_hydrolite():
    from hydrolite.real_project_model import assess_event_gate

    events = _event_rows(
        ["confirmed", "confirmed"],
        simulation_provenance_status="unknown_existing_output",
    )
    gate = assess_event_gate(events)

    assert gate["hydrolite_model_validated"] is False
    assert gate["independent_validation_ready"] is False
    assert "unknown_simulation_provenance" in gate["blockers"]


def test_diagnostic_metrics_cover_process_peak_timing_and_volume():
    from hydrolite.real_project_model import calculate_diagnostic_metrics

    timestamps = pd.date_range("2026-01-01", periods=5, freq="h")
    observed = pd.DataFrame(
        {"timestamp": timestamps, "flow_cms": [1.0, 2.0, 5.0, 3.0, 1.0]}
    )
    simulated = pd.DataFrame(
        {"timestamp": timestamps, "flow_cms": [1.1, 1.8, 4.5, 3.2, 1.2]}
    )

    metrics = calculate_diagnostic_metrics(
        "anonymous_event", observed, simulated, baseline_name="persistence"
    )

    expected = {
        "event_id",
        "baseline_name",
        "sample_count",
        "NSE",
        "KGE",
        "RMSE",
        "MAE",
        "PBIAS",
        "R2",
        "observed_peak_flow_cms",
        "simulated_peak_flow_cms",
        "peak_flow_error_percent",
        "peak_timing_error_hours",
        "observed_volume_m3",
        "simulated_volume_m3",
        "volume_error_percent",
    }
    assert expected <= metrics.keys()
    assert metrics["event_id"] == "anonymous_event"
    assert metrics["baseline_name"] == "persistence"
    assert metrics["sample_count"] == 5
    assert metrics["peak_timing_error_hours"] == 0.0
    assert metrics["observed_volume_m3"] > 0
    assert metrics["simulated_volume_m3"] > 0
    assert all(pd.notna(metrics[name]) for name in expected - {"event_id", "baseline_name"})


@pytest.mark.parametrize("mutation", ["content", "mtime"])
def test_external_source_checksum_or_mtime_drift_is_blocked(tmp_path: Path, mutation: str):
    from hydrolite.real_project import discover_real_project_data
    from hydrolite.real_project_model import guard_external_sources

    source_root = tmp_path / "anonymous-external-source"
    source_root.mkdir()
    source_file = source_root / "observed_flow.csv"
    source_file.write_text(
        "timestamp,flow_m3_s\n2026-01-01T00:00:00,1.0\n",
        encoding="utf-8",
    )
    inventory, paths = discover_real_project_data(source_root)

    if mutation == "content":
        source_file.write_text(
            "timestamp,flow_m3_s\n2026-01-01T00:00:00,2.0\n",
            encoding="utf-8",
        )
    else:
        stat = source_file.stat()
        os.utime(source_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))

    with pytest.raises(RuntimeError, match="external_data_changed_since_snapshot"):
        guard_external_sources(source_root, inventory, paths)


def test_scenario_comparison_uses_what_if_sensitivity_type():
    from hydrolite.real_project_model import build_scenario_comparison

    comparison = build_scenario_comparison(
        [
            {
                "scenario_id": "baseline",
                "parameter_change": "none",
                "peak_flow_cms": 10.0,
                "runoff_volume_m3": 36_000.0,
            },
            {
                "scenario_id": "cn_plus_5",
                "parameter_change": "curve_number:+5",
                "peak_flow_cms": 11.0,
                "runoff_volume_m3": 39_600.0,
            },
        ]
    )

    assert isinstance(comparison, pd.DataFrame)
    assert not comparison.empty
    assert set(comparison["scenario_type"]) == {"what_if_sensitivity_scenario"}


def test_scenario_comparison_requires_explicit_baseline():
    from hydrolite.real_project_model import build_scenario_comparison

    with pytest.raises(ValueError, match="explicit baseline"):
        build_scenario_comparison([{"scenario_id": "rainfall_high", "peak_flow_cms": 2.0}])


def test_processed_inputs_reuse_existing_input_builder_contract(tmp_path: Path):
    from hydrolite.input_builder import build_hydrolite_inputs
    from hydrolite.real_project_model import _register_processed_inputs
    from hydrolite.workspace import create_workspace, read_workspace_manifest

    workspace = tmp_path / "workspace"
    create_workspace(workspace, "Anonymous real project")
    data_dir = workspace / "standardized" / "m8b"
    data_dir.mkdir(parents=True)
    contents = {
        "rainfall.csv": "time,rain_mm\n2026-01-01,1\n",
        "observed_streamflow.csv": "datetime,gauge_id,observed_streamflow_m3s\n2026-01-01,G1,1\n",
        "subcatchments.csv": "id,area_km2,curve_number,lag_hours\nS1,1,75,1\n",
        "reaches.csv": "id,from,to,K_hours,X\nR1,S1,O,1,0.2\n",
    }
    for name, content in contents.items():
        (data_dir / name).write_text(content, encoding="utf-8")
    vector = workspace / "derived" / "m8b" / "basin.geojson"
    vector.parent.mkdir(parents=True)
    vector.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    _register_processed_inputs(workspace, {"data_dir": data_dir}, {"processed": [vector]})
    result = build_hydrolite_inputs(workspace, workspace / "models" / "m8b")
    manifest = read_workspace_manifest(workspace)

    assert result["status"] == "ready"
    assert {"rainfall_observed", "streamflow_observed", "subbasins", "reaches"} <= {
        row.get("user_declared_type") for row in manifest["datasets"]
    }
    assert all(row.get("standardized_path") for row in manifest["datasets"])


def test_real_data_diagnostic_is_a_delivery_validation_level():
    from hydrolite.product_status import VALIDATION_LEVELS

    assert "real_data_diagnostic" in VALIDATION_LEVELS


def test_real_project_model_keeps_water_quality_planned():
    from hydrolite.capability_registry import get_capability

    assert get_capability("water_quality")["status"] == "planned"


def test_real_project_model_does_not_touch_protected_trees():
    data_raw = ROOT / "data_raw"
    emergency = ROOT / "tmp_emergency_0722"
    before_data_raw = _tree_snapshot(data_raw)
    before_emergency = _tree_snapshot(emergency)

    from hydrolite.real_project_model import assess_event_gate, build_scenario_comparison

    assess_event_gate(_event_rows(["requires_confirmation"]))
    build_scenario_comparison([{"scenario_id": "baseline", "peak_flow_cms": 1.0}])

    assert _tree_snapshot(data_raw) == before_data_raw
    assert _tree_snapshot(emergency) == before_emergency
    assert "tmp_emergency_0722" not in (ROOT / ".gitignore").read_text(encoding="utf-8")
