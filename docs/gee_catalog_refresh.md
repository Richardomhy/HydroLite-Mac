# GEE Catalog Refresh Transport

HydroLite reads Earth Engine catalog metadata from the official Google Cloud
Storage bucket, not from Earth Engine compute APIs. The verified root object
is `gs://earthengine-stac/catalog/catalog.json`. The earlier
`https://storage.googleapis.com/earthengine-stac/catalog.json` candidate is
kept only as an unverified diagnostic candidate because it returns 404 in the
current environment.

Transport order is anonymous Google Cloud Storage, authenticated Google Cloud
Storage, `gcloud`, `gsutil`, then an official Google Storage HTTPS URL derived
from the verified object. GEE compute authentication and catalog metadata
transport are reported separately. A failed transport leaves the existing
catalog untouched and retains the seven-record `fixture_only` catalog.

`refresh dry-run` reads only the root catalog and writes nothing. `refresh
execute` traverses safe official child links into staging, validates the
candidate, then atomically activates a complete catalog. It never scrapes or
mirrors Google dataset HTML pages.
