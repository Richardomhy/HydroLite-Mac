# M9A.3 Data Acquisition Hub

## Scope and safety

The hub resolves data needs per requirement, checks standardized workspace data, discovers public candidates, and keeps download, approval, and project-measurement decisions separate. Public forcing or modeled products never become project-specific field evidence. This release does not implement pollutant delivery or transport.

Online requests are opt-in. Connector URLs use configured HTTPS host allowlists and reject credentials, non-public DNS addresses, unsafe redirects, unsupported media types, oversized payloads, and checksum mismatches. Downloaded files remain inert; archives are checked by the existing package-security code and are never executed. Raw downloads are cached outside the repository and imported to a workspace as `needs_mapping`; existing Data Center mapping, CRS/time handling, QC, and lineage remain the route to standardized data.

## CLI

```bash
python -m hydrolite data-connectors list
python -m hydrolite data-connectors health
python -m hydrolite data-connectors search gee config/search.yaml
python -m hydrolite data-requirements resolve SC10 /path/to/workspace
python -m hydrolite data-requirements resolve SC10 /path/to/workspace --online \\
  --bbox WEST SOUTH EAST NORTH --dates 2024-01-01 2024-12-31 --maximum-resolution-m 30
python -m hydrolite data-requirements missing /path/to/resolution_manifest.json
```

The search YAML contains bounded query fields such as `data_type`, `bbox`, `start`, `end`, and an explicit `online: true`. Omitting `online` keeps discovery offline. STAC requests need a bounded bbox; the Data Center exposes optional bbox, date, and maximum-pixel-size fields for online discovery. Fetching requires a resolver manifest and a separate `--execute` acknowledgement; large items require `--confirm-large` as well.

For the audited Gaoqiao requests:

```bash
python -m hydrolite data-requirements resolve gaoqiao_m9a2 /path/to/gaoqiao-workspace \
  --m9a2-dir output/water_environment/m9a2
```

This reads only the M9A.2 request/factor packages and manifest; it does not rescan historical source documents. It writes the requirement manifest, a workbook of genuinely user-required data, minimal CSV templates, and a Gaoqiao classification report under the workspace reports directory.

## Resolution meanings

| Strategy | Meaning |
|---|---|
| `AUTO_FETCH` | A trusted, licensed candidate meets the hard requirement checks. Fetch is still an explicit user action; successful fetch is not QC readiness. |
| `AUTO_DISCOVER_REQUIRE_APPROVAL` | Candidate metadata can be surfaced, but a person must approve project applicability before it becomes a project input. |
| `USER_REQUIRED` | Public information cannot substitute for project-specific evidence, measurements, or approval. |

Statuses distinguish local standardized/QC-ready data, data needing QC, fetchable candidates, candidates requiring review, project measurements, unsupported requirements, and unavailable sources. Resolution rates count requirements, not files.

## Connectors and limitations

The registry retains local, Earth Engine, Earthdata, CDS, and STAC connectors and adds bounded generic HTTP/STAC plus meteorology, hydrology-observation, environmental-monitoring, and regulatory interfaces. The latter interfaces report `provider_not_configured` or `unavailable` where no verified public API is configured; the hub does not fabricate observations or scrape login/paywall pages.

Earth Engine catalog metadata is distinct from Earth Engine computation authentication. Catalog results may be browsed while compute/export remains `authentication_required`. The configured generic STAC collection is a small DEM discovery path, not a global catalog mirror. Automatic CRS reprojection and provider-specific rainfall conversion are not performed by the acquisition layer; downloaded assets must pass existing Data Center standardization and QC before model use.

## Cache and provenance

Set `HYDROLITE_DATA_CACHE_ROOT` or configure `data_cache_root` to a writable external cache location. The default is under the HydroLite runtime directory. If a configured `/Volumes/...` root is unavailable, the cache reports `data_cache_storage_unavailable` and does not silently move data to the system disk. Policies are `reuse_if_unchanged` (default), `refresh_if_stale`, `force_refresh`, and `offline_only`. Each fetched artifact records provider, dataset/version, retrieval time, ETag/Last-Modified when present, license, processing chain, and SHA-256. Snapshot metadata pins this provenance; new source versions do not silently replace prior project versions.

Unknown or restricted licenses may remain as references but cannot be fetched automatically or bundled into a portable project. Cache contents, workspaces, and real downloaded datasets are runtime data and must not be committed.

## Gaoqiao result

The M9A.2 request resolver keeps six project requirements as `USER_REQUIRED`: source coordinate/CRS confirmation, actual outfall flow, same-source concentration evidence, verified receiving reach/water relation, wastewater volume, and project-specific factor approval. Existing public factor references are candidates only and remain `approval_required`; they do not remove the project approval gate. No M9B eligibility or gate is changed by acquisition discovery.
