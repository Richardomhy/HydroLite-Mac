# GEE Connector

The connector reuses HydroLite's Earth Engine diagnostics and `config/data_sources/gee_datasets.yaml`. It supports bounded plans for DEM, rainfall, temperature, evapotranspiration, soil moisture, land cover, NDVI, surface water and imagery.

Authentication stays in Earth Engine user configuration. Set `GEE_PROJECT` locally. Unbounded export is rejected.
