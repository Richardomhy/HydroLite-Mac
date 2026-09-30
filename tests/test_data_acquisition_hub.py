from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json

import pandas as pd
import pytest


def _candidate(**overrides):
    from hydrolite.connectors.contracts import DatasetCandidate
    values = dict(dataset_id="public/rain-v1", connector_id="http", provider="Example Public Data",
                  data_type="rainfall_observed", source_url="https://data.example.test/rain.csv",
                  version="v1", variables=("precipitation",), license="CC-BY-4.0",
                  license_status="known", trusted_provider=True, access_status="public_download",
                  estimated_size=20, content_type="text/csv", checksum="")
    values.update(overrides)
    return DatasetCandidate(**values)


def test_contracts_registry_health_and_optional_provider_states():
    from hydrolite.connectors import DataConnectorRegistry, DataRequirement
    from hydrolite.connectors.contracts import STRATEGIES
    requirement = DataRequirement("r1", "dem", fallback_strategy="AUTO_FETCH")
    assert requirement.fallback_strategy in STRATEGIES
    rows = {row["connector_id"]: row for row in DataConnectorRegistry().health()}
    assert rows["gee"]["catalog"]["status"] in {"available", "fixture_only", "partial", "official_complete"}
    assert rows["gee"]["compute_status"] == "authentication_required"
    assert rows["hydrology_observations"]["reason"] == "provider_not_configured"
    assert rows["environmental_monitoring"]["access_status"] == "unavailable"


def test_requirement_resolution_never_substitutes_public_data_for_project_measurement(tmp_path):
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.data_requirement_resolver import resolve_requirement
    from hydrolite.workspace import create_workspace
    workspace = tmp_path / "w"
    create_workspace(workspace, "measurements")
    req = DataRequirement("actual-flow", "outfall_actual_flow", required_fields=("source_id", "flow"),
                          requires_project_measurement=True)
    result = resolve_requirement(req, workspace)
    assert result["strategy"] == "USER_REQUIRED"
    assert result["status"] == "project_measurement_required"


def test_local_ready_requires_standardized_qc_and_checksum(tmp_path):
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.data_requirement_resolver import resolve_requirement
    from hydrolite.workspace import create_workspace, read_workspace_manifest, write_workspace_manifest, calculate_file_checksum
    workspace = tmp_path / "w"
    create_workspace(workspace, "local")
    path = workspace / "standardized" / "rain.csv"
    path.parent.mkdir(exist_ok=True)
    path.write_text("timestamp,rainfall_mm\n2026-01-01,1\n")
    manifest = read_workspace_manifest(workspace)
    manifest["datasets"] = [{"dataset_id": "rain-1", "user_declared_type": "rainfall_observed",
                             "quality_status": "ready", "standardized_path": "standardized/rain.csv",
                             "standardized_checksum": calculate_file_checksum(path)}]
    write_workspace_manifest(workspace, manifest)
    req = DataRequirement("rain", "rainfall", required_fields=("timestamp", "rainfall_mm"))
    assert resolve_requirement(req, workspace)["status"] == "local_ready"
    path.write_text("timestamp,rainfall_mm\n2026-01-01,2\n")
    assert resolve_requirement(req, workspace)["status"] != "local_ready"


def test_requirement_rates_count_requirements_and_report_only_unobtainable(tmp_path):
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.data_requirement_resolver import resolve_scenario_requirements, write_resolution
    from hydrolite.workspace import create_workspace
    workspace = tmp_path / "w"
    create_workspace(workspace, "report")
    requirements = [
        DataRequirement("measured", "outfall_actual_flow", requires_project_measurement=True),
        DataRequirement("factor", "emission_factors", fallback_strategy="AUTO_DISCOVER_REQUIRE_APPROVAL"),
    ]
    result = resolve_scenario_requirements("test", workspace, requirements=requirements)
    assert result["metrics"]["requirements_evaluated"] == 2
    assert result["metrics"]["user_required_rate"] == 0.5
    path = write_resolution(result, workspace / "reports" / "resolution")
    frame = pd.read_excel(path.parent / "user_required_data.xlsx")
    assert frame["requirement"].tolist() == ["measured", "factor"]
    assert (path.parent / "data_acquisition_readiness_report_zh.md").is_file()


def test_requirement_reports_network_blocked_without_fabricating_resolution(tmp_path):
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.data_requirement_resolver import resolve_scenario_requirements
    from hydrolite.workspace import create_workspace

    class Registry:
        def capabilities(self): return {"stac": ["dem"]}
        def recommend(self, *_args): return {"candidates": [], "searches": [{"connector_id": "stac", "status": "non_public_resolution"}]}

    workspace = tmp_path / "w"
    create_workspace(workspace, "network")
    req = DataRequirement("dem", "dem", allow_auto_fetch=True, fallback_strategy="AUTO_FETCH")
    result = resolve_scenario_requirements("dem", workspace, Registry(), requirements=[req])
    assert result["requirements"][0]["status"] == "network_blocked"
    assert "非公网" in result["requirements"][0]["reason"]
    assert result["metrics"]["automatic_data_resolution_rate"] == 0
    assert result["metrics"]["network_blocked"] == 1


def test_gaoqiao_m9a2_flat_package_layout_preserves_gates(tmp_path):
    from hydrolite.data_requirement_resolver import resolve_point_source_requests
    from hydrolite.workspace import create_workspace

    workspace = tmp_path / "workspace"
    create_workspace(workspace, "gaoqiao")
    package = tmp_path / "m9a2"
    package.mkdir()
    gates = {"source_load": "ready_with_warnings", "point_source": "blocked"}
    (package / "m9a2_manifest.json").write_text(json.dumps({"gates": gates}))
    pd.DataFrame({"request_id": [f"DR0{i}" for i in range(1, 7)]}).to_excel(
        package / "m9a2_project_data_request_pack.xlsx", index=False
    )
    pd.DataFrame(columns=["factor_id", "source_reference"]).to_excel(
        package / "factor_decision_pack.xlsx", index=False
    )

    result = resolve_point_source_requests(workspace, package, tmp_path / "reports", online=True)
    assert result["m9a2_gates_unchanged"] == gates
    assert [row["requirement"]["requirement_id"] for row in result["requirements"][:6]] == [f"DR0{i}" for i in range(1, 7)]
    assert all(row["strategy"] == "USER_REQUIRED" for row in result["requirements"][:6])


def test_cache_fetch_checks_hash_and_reuses_verified_content(tmp_path, monkeypatch):
    import hydrolite.dataset_cache as cache_module
    from hydrolite.dataset_cache import DatasetCache
    body = b"timestamp,rainfall_mm\n2026-01-01,1\n"

    class Response(BytesIO):
        code = 200
        headers = {"Content-Type": "text/csv", "Content-Length": str(len(body)), "ETag": '"v1"'}

    @contextmanager
    def fake_open(*args, **kwargs):
        yield Response(body)

    monkeypatch.setattr(cache_module, "open_public", fake_open)
    cache = DatasetCache(tmp_path / "external-cache", max_bytes=1024)
    candidate = _candidate()
    first = cache.fetch(candidate, ["data.example.test"])
    assert first["status"] == "fetched"
    assert first["checksum"] == sha256(body).hexdigest()
    assert cache.fetch(candidate, ["data.example.test"], policy="offline_only")["status"] == "offline_cached"
    assert cache.lookup(candidate)["checksum"] == first["checksum"]


def test_cache_rejects_checksum_mismatch_and_license_unknown(tmp_path, monkeypatch):
    import hydrolite.dataset_cache as cache_module
    from hydrolite.dataset_cache import DatasetCache
    body = b"safe csv"

    class Response(BytesIO):
        code = 200
        headers = {"Content-Type": "text/csv", "Content-Length": str(len(body))}

    @contextmanager
    def fake_open(*args, **kwargs):
        yield Response(body)

    monkeypatch.setattr(cache_module, "open_public", fake_open)
    cache = DatasetCache(tmp_path / "cache", max_bytes=1024)
    mismatch = cache.fetch(_candidate(checksum="0" * 64), ["data.example.test"])
    assert mismatch["status"] == "checksum_mismatch"
    unknown = _candidate(license_status="unknown")
    from hydrolite.connectors.public import HttpFileConnector
    result = HttpFileConnector({"allowed_hosts": ["data.example.test"]}).fetch(unknown, cache=cache)
    assert result["status"] == "approval_required"


def test_url_and_cache_path_security(monkeypatch, tmp_path):
    from hydrolite.connectors.transport import ConnectorError, validate_public_url
    from hydrolite.dataset_cache import DatasetCache
    with pytest.raises(ConnectorError):
        validate_public_url("http://data.example.test/a.csv", ["data.example.test"])
    with pytest.raises(ConnectorError):
        validate_public_url("https://127.0.0.1/a.csv", ["127.0.0.1"])
    with pytest.raises(ConnectorError):
        DatasetCache(tmp_path / "data_raw" / "cache")


def test_online_import_records_lineage_and_needs_data_center_qc(tmp_path):
    from hydrolite.data_acquisition import import_fetched_dataset
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.workspace import create_workspace, list_workspace_datasets
    workspace = tmp_path / "workspace"
    create_workspace(workspace, "online")
    raw = tmp_path / "cache" / "rain.csv"
    raw.parent.mkdir()
    raw.write_text("date,precipitation_mm\n2026-01-01,1\n")
    checksum = sha256(raw.read_bytes()).hexdigest()
    result = import_fetched_dataset({
        "local_path": str(raw), "checksum": checksum, "retrieved_at": "2026-01-02T00:00:00+00:00",
        "candidate": {"dataset_id": "rain-v1", "provider": "public", "data_type": "rainfall_observed",
                      "version": "v1", "license": "CC-BY-4.0", "license_status": "known"},
    }, workspace, DataRequirement("rain", "rainfall_observed"))
    assert result["quality_status"] == "needs_mapping"
    assert result["project_measurement_confirmed"] is False
    assert len(list_workspace_datasets(workspace)) == 1


def test_stac_generic_search_uses_configured_endpoint_and_license_metadata(monkeypatch):
    from contextlib import contextmanager
    from io import BytesIO
    from hydrolite.connectors.public import GenericStacAdapter
    collection = {"license": "CC-BY-4.0"}
    item = {"features": [{"id": "tile-1", "collection": "cop-dem-glo-30", "bbox": [0, 0, 1, 1],
                          "properties": {"datetime": "2025-01-01T00:00:00Z", "gsd": 30},
                          "assets": {"data": {"href": "https://copernicus-dem-30m.s3.amazonaws.com/a.tif",
                                              "roles": ["data"], "type": "image/tiff"}}}]}

    class Response(BytesIO):
        pass

    @contextmanager
    def fake_open(url, *args, **kwargs):
        payload = collection if "/collections/" in url else item
        yield Response(json.dumps(payload).encode())

    monkeypatch.setattr("hydrolite.connectors.public.open_public", fake_open)
    connector = GenericStacAdapter({"endpoint": "https://earth-search.aws.element84.com/v1",
                                    "allowed_hosts": ["earth-search.aws.element84.com", "copernicus-dem-30m.s3.amazonaws.com"],
                                    "trusted": True, "provider": "Earth Search",
                                    "collections": {"dem": "cop-dem-glo-30"}})
    result = connector.search({"online": True, "data_type": "dem", "bbox": [0, 0, 1, 1]})
    assert result["status"] == "available"
    candidate = result["candidates"][0]
    assert candidate.license_status == "known"
    assert candidate.resolution == 30


def test_stac_relative_asset_href_resolves_from_item_self_link(monkeypatch):
    from contextlib import contextmanager
    from io import BytesIO
    from hydrolite.connectors.public import GenericStacAdapter

    payloads = {
        "/collections/dem": {"license": "CC-BY-4.0"},
        "/search?collections=dem&limit=5&bbox=0%2C0%2C1%2C1": {
            "features": [{"id": "tile", "bbox": [0, 0, 1, 1],
                "links": [{"rel": "self", "href": "https://stac.example.test/collections/dem/items/tile.json"}],
                "assets": {"elevation": {"href": "../../assets/tile.tif", "roles": ["data"], "type": "image/tiff"}}}]
        },
    }

    @contextmanager
    def fake_open(url, *args, **kwargs):
        yield BytesIO(json.dumps(next(value for key, value in payloads.items() if key in url)).encode())

    monkeypatch.setattr("hydrolite.connectors.public.open_public", fake_open)
    connector = GenericStacAdapter({"endpoint": "https://stac.example.test", "allowed_hosts": ["stac.example.test", "assets.example.test"],
                                    "trusted": True, "provider": "fixture", "collections": {"dem": "dem"}})
    candidate = connector.search({"online": True, "data_type": "dem", "bbox": [0, 0, 1, 1]})["candidates"][0]
    assert candidate.source_url == "https://stac.example.test/collections/assets/tile.tif"


def test_portable_project_rejects_unknown_license_online_dataset(tmp_path, monkeypatch):
    from hydrolite.workspace import create_workspace, read_workspace_manifest, write_workspace_manifest
    from hydrolite.deliverable_package import validate_portable_data_licenses
    workspace = tmp_path / "project"
    create_workspace(workspace, "license")
    source = tmp_path / "data.csv"
    source.write_text("a\n1\n")
    manifest = read_workspace_manifest(workspace)
    manifest["datasets"] = [{"dataset_id": "online", "source_type": "online_public",
                             "cache_reference": str(source), "license_status": "unknown"}]
    write_workspace_manifest(workspace, manifest)
    with pytest.raises(ValueError, match="license"):
        validate_portable_data_licenses(workspace, [source])


def test_requirement_ranking_and_rates_are_requirement_based(tmp_path):
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.data_requirement_resolver import resolve_scenario_requirements

    candidate = _candidate(data_type="rainfall", variables=("rainfall",), license_status="known")

    class Registry:
        def recommend(self, requirement, config):
            return {"candidates": [{"candidate": candidate.as_dict(), "eligible": True, "score": 7}], "searches": []}

        def capabilities(self):
            return {"http": ["rainfall"]}

    workspace = tmp_path / "w"
    from hydrolite.workspace import create_workspace
    create_workspace(workspace, "rates")
    requirements = [DataRequirement("rain", "rainfall", allow_auto_fetch=True),
                    DataRequirement("unknown", "unknown_series")]
    result = resolve_scenario_requirements("test", workspace, requirements=requirements, registry=Registry())
    assert [row["status"] for row in result["requirements"]] == ["auto_fetch_available", "unsupported"]
    assert result["metrics"]["requirements_evaluated"] == 2
    assert result["metrics"]["automatic_data_resolution_rate"] == 0.5
    assert result["metrics"]["user_required_rate"] == 0.5


def test_fetch_never_executes_approval_or_user_required_candidates(tmp_path):
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.data_requirement_resolver import fetch_recommended

    class Registry:
        fetched = False

        def fetch(self, *args, **kwargs):
            self.fetched = True
            return {"status": "fetched"}

    workspace = tmp_path / "w"
    from hydrolite.workspace import create_workspace
    create_workspace(workspace, "gates")
    candidate = _candidate(data_type="emission_factors", access_status="approval_required").as_dict()
    requirements = [DataRequirement("factor", "emission_factors", fallback_strategy="AUTO_DISCOVER_REQUIRE_APPROVAL"),
                    DataRequirement("flow", "outfall_actual_flow", requires_project_measurement=True)]
    resolution = {"requirements": [{"requirement": req.as_dict(), "candidates": [{"candidate": candidate, "eligible": True}]} for req in requirements]}
    registry = Registry()
    results = fetch_recommended(resolution, workspace, registry)
    assert [row["status"] for row in results] == ["approval_required", "approval_required"]
    assert registry.fetched is False


def test_canonical_online_table_uses_existing_time_and_field_mapping():
    from hydrolite.data_acquisition import canonical_online_table

    frame = pd.DataFrame({"date": ["2026-01-01T00:00:00Z"], "precipitation_mm": [4.0]})
    result = canonical_online_table(frame, "rainfall_observed", {"provider": "fixture", "version": "v1"})
    assert pd.api.types.is_datetime64_any_dtype(result["date"])
    assert str(result["date"].dt.tz) == "UTC"
    assert result.attrs["online_provenance"]["version"] == "v1"


def test_scenario_requirement_contract_and_project_evidence_strategy():
    from hydrolite.data_requirement_resolver import classify_requirement_source, requirements_for_scenario

    point = requirements_for_scenario("water_environment_source_accounting")
    by_id = {item.requirement_id: item for item in point}
    assert set(by_id) == {"DR01", "DR02", "DR03", "DR04", "DR05", "DR06", "public_factor_references"}
    assert all(classify_requirement_source(by_id[key]) == "USER_REQUIRED" for key in ("DR01", "DR02", "DR03", "DR04", "DR05", "DR06"))
    assert classify_requirement_source(by_id["public_factor_references"]) == "AUTO_DISCOVER_REQUIRE_APPROVAL"
    assert len(requirements_for_scenario("SC10")) == 7
