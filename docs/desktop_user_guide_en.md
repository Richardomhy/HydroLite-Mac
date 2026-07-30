# HydroLite Studio macOS Desktop Guide

Use “Historical Flood Validation” for event catalogs, QC, hindcasts, assimilation, lead-time checks, and reports. Historical Flood Validation and Data Assimilation are partial capabilities; the desktop may run bounded local batches while cloud mode primarily displays prepared outputs.

Drag the app from the DMG to Applications, launch it from Finder, and wait for the local backend health check. Use Project Center, Data Center, and Run Center for normal work. Data lives in `~/Library/Application Support/HydroLite Studio/`; logs live in `~/Library/Logs/HydroLite Studio/`.

Quit from the app menu for a clean backend shutdown. QGIS, HEC-HMS, GEE, and connectors remain optional external capabilities. Version 0.7.0-dev is a development channel; the ad-hoc package is for local validation.

Use “Drought Analysis and Forecast” for the daily balance, PET, soil/groundwater state, SPI/SPEI/SSI, event catalog, freshness-aware status, bounded scenarios, and assimilation artifacts. The isolated environment is `hydrolite-science`; diagnostic classes are not statutory warnings.
