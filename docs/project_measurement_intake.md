# Project Measurement Intake Hub

HydroLite separates three evidence classes: **公开数据** are external products and metadata; **项目实测/调查数据** are source-, location- and period-specific records supplied by the project team; **项目审批参数** are project decisions with a named reviewer. A public dataset or successful download never substitutes for a required project measurement.

## Supported intake

M10A provides six versioned templates: MR01 `point_source_identity_v1`, MR02 `point_source_flow_v1`, MR03 `point_source_concentration_v1`, MR04 `receiving_water_reach_v1`, MR05 `wastewater_facility_operation_v1`, and MR06 `factor_approval_v1`. Excel templates use row 1 for canonical headers, row 2 for Chinese field descriptions, and row 3 for units/formats. CSV is also accepted. Pollutants are CODMn, NH3-N, TN and TP; concentrations normalize to mg/L. A `<DL` value retains its qualifier and is not replaced with zero.

## Review lifecycle

`USER_REQUIRED → template → upload → row validation and preview → human review → project measurement registry → lineage and snapshot → existing resolver refresh`.

Only `.csv` and `.xlsx` files up to 50 MiB are accepted. Macro-enabled workbooks, workbook external links/connections, unsafe ZIP paths and oversized expansion are rejected. Uploaded originals are stored read-only in the existing project's `measurements/originals/`; normalized derivatives are stored separately. A duplicate SHA-256 is not imported twice. Revisions create a new submission; a prior accepted submission becomes superseded only after its replacement is accepted.

CRS, reach relation and factor decisions require human evidence. WGS84/EPSG:4326 coordinate bounds are checked, but coordinate ranges do not establish CRS. GCJ-02 and BD-09 are not treated as EPSG:4326 and are never silently transformed. Nearest-reach matches are candidates only. MR06 calls the existing M9A.1 `approve_factor` decision API; the decision is project-specific, not a claim of universal scientific validity.

## CLI

```bash
python -m hydrolite measurements requirements <project-workspace>
python -m hydrolite measurements templates <project-workspace>
python -m hydrolite measurements validate <file> --requirement MR03
python -m hydrolite measurements import <file> --project <project-workspace> --requirement MR03
python -m hydrolite measurements review <submission-id> --project <project-workspace> --action accept --reviewer <name> --comment "Reviewed against source record"
python -m hydrolite measurements refresh <project-workspace>
```

`import` creates a submission and validation preview; it does not accept the evidence. Accepted rows enter the existing workspace registry, data-lineage graph and project-version snapshot. Rejected and upload-only records do not create snapshots. The resolver refresh never offers a manual “ready” override. `point_source_delivery`, diffuse delivery and M9B remain controlled by the existing M9A.1/M9A.2 gates; M10A never starts M9B.

## Storage and limitations

An unavailable workspace/external volume blocks upload with `project_storage_unavailable`; HydroLite will not fall back to a repository or Macintosh HD scratch directory. No user/account service is provided; a local reviewer name and non-empty comment are audit metadata, not IAM. Project records are not copied into the repository. Intake readiness is not a pollution-transport model or water-quality forecast; `water_quality` remains planned.
