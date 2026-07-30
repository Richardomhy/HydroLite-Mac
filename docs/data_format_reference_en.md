# Data Format Reference

Tables/time series support CSV, TSV, XLSX and JSON. Excel requires explicit sheet/header selection. Vectors support GeoJSON, ZIP Shapefile, GPKG, KML/KMZ and coordinate CSV; Shapefiles require SHP/SHX/DBF/PRJ, while KML/KMZ use WGS84. Rasters support GeoTIFF, ASCII Grid, NetCDF and HDF5 with optional backends.

Rainfall semantics must distinguish cumulative, interval increment and intensity. Unknown CRS or units require confirmation. DSS remains a local reference and is excluded from bundles.
