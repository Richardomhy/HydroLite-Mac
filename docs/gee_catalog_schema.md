# GEE Catalog Schema

HydroLite stores normalized metadata, not imagery. Each record carries the Earth Engine asset ID, official dataset page, STAC source, provider, time and envelope metadata, resolution, bands, license/citation fields, status, replacement IDs, use cases, source hash, refresh time and warnings.

Missing metadata is `null` and recorded as a warning. A catalog envelope indicates metadata-level overlap or coverage only; it is not a pixel-footprint guarantee.

The repository fixture is deliberately small and labelled `fixture_only`. Full local catalog files live under `~/.hydrolite/catalogs/gee/` (or the macOS Application Support path) and are not tracked.
