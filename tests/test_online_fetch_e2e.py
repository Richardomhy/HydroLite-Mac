from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from tests.runtime_helpers import configure_runtime


def test_loopback_fetch_qc_lineage_snapshot_cache_replay_and_version_freeze(tmp_path, monkeypatch):
    from hydrolite.connectors.contracts import DataRequirement, DatasetCandidate
    from hydrolite.connectors.public import HttpFileConnector
    from hydrolite.connectors.transport import NetworkSecurityPolicy
    from hydrolite.dataset_cache import DatasetCache
    from hydrolite.data_acquisition import import_fetched_dataset
    from hydrolite.data_quality_center import run_dataset_quality_checks
    from hydrolite.data_requirement_resolver import resolve_requirement
    from hydrolite.input_builder import build_all_inputs
    from hydrolite.project_versioning import create_data_snapshot
    from hydrolite.runtime_db import get_data_snapshot_record
    from hydrolite.workspace import create_workspace, read_workspace_manifest, calculate_file_checksum

    configure_runtime(monkeypatch, tmp_path)
    current_body = [b"timestamp,subbasin_id,rainfall_mm\n2026-01-01T00:00:00Z,S1,2\n2026-01-01T01:00:00Z,S1,4\n"]
    request_count = [0]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request_count[0] += 1
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Length", str(len(current_body[0])))
            self.end_headers()
            self.wfile.write(current_body[0])

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        candidate = DatasetCandidate(
            dataset_id="fixture-rain", connector_id="http", provider="local-test-fixture",
            data_type="rainfall_observed", source_url=f"http://{host}:{port}/rainfall.csv",
            version="v1", variables=("rainfall_mm",), license="CC-BY-4.0",
            license_status="known", trusted_provider=True, access_status="public_download",
            estimated_size=len(current_body[0]), content_type="text/csv",
            metadata={"source_reference": "isolated loopback fixture", "synthetic_demo": True},
        )
        cache = DatasetCache(tmp_path / "external-cache", max_bytes=1024)
        connector = HttpFileConnector({"allowed_hosts": [host], "provider": "local-test-fixture", "trusted": True})
        fetched_v1 = connector.fetch(candidate, cache=cache, network_policy=NetworkSecurityPolicy.TEST_LOOPBACK_ALLOWED)
        assert fetched_v1["status"] == "fetched"
        assert fetched_v1["checksum"] == calculate_file_checksum(fetched_v1["local_path"])
        assert request_count[0] == 1
        assert connector.fetch(candidate, cache=cache, network_policy=NetworkSecurityPolicy.TEST_LOOPBACK_ALLOWED)["status"] == "cached"
        assert request_count[0] == 1
        assert cache.fetch(candidate, [host], policy="offline_only")["status"] == "offline_cached"

        workspace = tmp_path / "workspace"
        create_workspace(workspace, "Fixture acquisition")
        requirement = DataRequirement("rainfall", "rainfall_observed", required_fields=("timestamp", "rainfall_mm"))
        imported_v1 = import_fetched_dataset(fetched_v1, workspace, requirement)
        quality_v1 = run_dataset_quality_checks(imported_v1["dataset_id"], workspace)
        assert quality_v1["quality_status"] in {"ready", "ready_with_warnings"}
        manifest_v1 = read_workspace_manifest(workspace)
        source_record_v1 = next(row for row in manifest_v1["datasets"] if row["dataset_id"] == imported_v1["dataset_id"])
        assert source_record_v1["standardized_path"]
        assert source_record_v1["online_provenance"]["checksum"] == fetched_v1["checksum"]
        assert source_record_v1["license_status"] == "known"
        assert resolve_requirement(requirement, workspace, online=False)["status"] == "offline_cached"

        build = build_all_inputs(workspace, tmp_path / "input-builder")
        hydro = next(row for row in build["models"] if row["model_id"] == "hydrolite_event_model")
        assert hydro["status"] == "incomplete"  # rainfall is usable; unrelated subbasin/reach inputs are honestly missing.
        assert "rainfall_observed" in hydro["files"]
        snapshot_v1 = create_data_snapshot(workspace)
        old_checksum = snapshot_v1["checksum"]
        old_dataset_checksums = dict(snapshot_v1["checksums"])

        current_body[0] = b"timestamp,subbasin_id,rainfall_mm\n2026-01-01T00:00:00Z,S1,3\n2026-01-01T01:00:00Z,S1,5\n"
        candidate_v2 = DatasetCandidate(**{**candidate.as_dict(), "version": "v2", "metadata": {"source_reference": "isolated loopback fixture", "synthetic_demo": True}})
        fetched_v2 = connector.fetch(candidate_v2, cache=cache, network_policy=NetworkSecurityPolicy.TEST_LOOPBACK_ALLOWED)
        assert fetched_v2["status"] == "fetched"
        assert fetched_v2["checksum"] != fetched_v1["checksum"]
        assert fetched_v1["local_path"] != fetched_v2["local_path"]
        assert calculate_file_checksum(fetched_v1["local_path"]) == fetched_v1["checksum"]
        imported_v2 = import_fetched_dataset(fetched_v2, workspace, requirement)
        assert run_dataset_quality_checks(imported_v2["dataset_id"], workspace)["quality_status"] in {"ready", "ready_with_warnings"}
        snapshot_v2 = create_data_snapshot(workspace)
        assert snapshot_v2["checksum"] != old_checksum
        frozen_v1 = get_data_snapshot_record(snapshot_v1["snapshot_id"])
        assert frozen_v1["checksum"] == old_checksum
        assert frozen_v1["checksums"] == old_dataset_checksums
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
