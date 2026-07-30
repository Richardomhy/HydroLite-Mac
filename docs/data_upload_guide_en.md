# Data Upload Guide

HydroLite event runs require rainfall, subbasin and reach tables. Observed flow is optional but recommended. SWMM needs an INP file; reservoir routing needs stage-area-volume and stage-discharge curves; the future water-quality interface needs observations, flow and source data.

Create a workspace, download a template, upload files, inspect the preview/checksum, confirm uncertain mapping/units/CRS, run quality checks, review missing requirements, then build inputs. Only `ready` or `ready_with_warnings` standardized/derived data enters the builder.

Raw uploads are read-only. Missing values are not converted to zero. Credentials stay in the user home directory or environment. External downloads require a bounded request and explicit execution.
