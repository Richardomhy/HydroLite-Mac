# Phase 1 Acceptance

HydroLite-Mac Phase 1 MVP includes the following completed capabilities.

## Modeling

- SCS-CN runoff generation from rainfall and curve number inputs.
- Simplified triangular unit hydrograph routing for subbasin runoff.
- Muskingum channel routing for reach flow propagation.
- Muskingum parameter validation:
  - `K > 0`
  - `0 <= X <= 0.5`
  - `dt > 0`
  - `2*K*X <= dt <= 2*K*(1-X)`
  - all values are interpreted in hours for `dt` and `K`.
- Water balance checking with `water_balance.xlsx`:
  - `subbasin_balance`
  - `outlet_balance`
  - warning when absolute balance error exceeds 5%.

## Workflows

- Single-case execution:

```bash
python -m hydrolite run cases/demo.yaml
```

- Batch execution for all `.yaml` and `.yml` files in `cases/`:

```bash
python -m hydrolite batch cases/
```

- Local Streamlit interface:

```bash
python -m streamlit run hydrolite/ui/app.py --server.headless true
```

## Outputs

- Per-case outputs in `output/<case_name>/`:
  - `result_flow.csv`
  - `summary.xlsx`
  - `hydrograph.png`
  - `water_balance.xlsx`
  - `run.log`
- Batch summary:
  - `output/batch_summary.xlsx`

## Tests

The Phase 1 test suite covers hydrology formulas, routing validation, water balance outputs, batch execution, Streamlit helper functions, and `data_raw` immutability checks.

Current health-check command:

```bash
pytest -q
```

Expected status at snapshot time:

```text
23 passed
```

## Data Safety

`data_raw/` is treated as read-only original data. Demo and test data are stored separately in `data_demo/`, and generated files are written to `output/`.

