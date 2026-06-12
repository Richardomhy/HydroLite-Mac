# Known Limitations

- HydroLite Studio v0.5.0-alpha is not a complete replacement for MIKE or other professional hydrodynamic suites.
- OpenHydroNet currently produces an input package only; it does not perform real AI flood prediction.
- GEE features require a user Google Earth Engine account, Google Cloud project, enabled Earth Engine API, and local credentials.
- SWMM execution in cloud environments may be limited by Python binary dependency availability.
- `data_demo/observed/demo_observed_streamflow.csv` is synthetic/demo only and is not real gauge data.
- GEE-derived parameter suggestions are heuristic and are not calibrated model parameters.
- Engineering design and regulatory review require manual expert verification.
- The demo basin and demo data are intentionally small and are not representative of production-scale studies.
- Streamlit Community Cloud is best for demonstration and review; full local modeling is recommended for SWMM/GEE/OpenHydroNet backend workflows.
