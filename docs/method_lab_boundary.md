# Method Lab Safety Boundary

HydroLite method experiments are clean-room implementations of general ideas. They do not reproduce paper architectures, training settings, figures, datasets, or third-party Skill assets.

- `data_raw/` and `tmp_emergency_0722/` are protected and never model-lab inputs or outputs.
- GEE catalog snapshots contain metadata only; authentication is required for Earth Engine computation.
- Synthetic demonstrations are software checks, not real-project validation.
- Physical HydroLite water-balance outputs remain authoritative. Feature and residual layers are parallel experimental outputs.
- `water_quality` remains `planned`; `flood_forecast` and `drought_forecast` remain `partial`.
- Tracked source must not include credentials, external checkouts, model weights, DSS/HDF5, paper PDFs, or copied third-party Skill assets.
- `config/research_sources.yaml` is the machine-readable clean-room policy used by baseline tests.
