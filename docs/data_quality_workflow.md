# Data Quality Workflow

Checks cover format, schema, units, temporal/spatial consistency, missing values, duplicates, ranges, provenance, license and model compatibility.

States are `ready`, `ready_with_warnings`, `needs_mapping`, `needs_repair`, `incomplete`, `invalid` and `unsupported`. Low-confidence mapping is never promoted automatically. Missing data remains missing. Repair and conversion outputs go to `standardized/` or `derived/`, never `raw/`.
