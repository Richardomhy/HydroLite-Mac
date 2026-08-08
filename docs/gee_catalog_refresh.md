# GEE Catalog Refresh

The only catalog root is `gs://earthengine-stac/catalog.json`, accessed through `https://storage.googleapis.com/earthengine-stac/catalog.json`. Refresh accepts only the Google Storage and Earth Engine dataset-page domains.

`refresh dry-run` checks the official root and writes nothing. `refresh execute` builds a staged candidate, validates it, requires more records than the fixture, then activates it while retaining a backup. A failed candidate leaves the previous local catalog untouched. Earth Engine authentication is not required for catalog operations.
