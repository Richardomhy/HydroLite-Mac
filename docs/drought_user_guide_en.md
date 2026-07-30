# HydroLite Drought Analysis Guide

Run the daily continuous model first and verify its water-balance gate. Then calculate indices, build the historical event catalog, assess data freshness, run bounded scenarios or published forecast inputs, and report uncertainty.

```bash
conda run -n hydrolite-science python -m hydrolite continuous run data_demo/drought/continuous_model_config.yaml
conda run -n hydrolite-science python -m hydrolite drought forecast-demo
conda run -n hydrolite-science python -m hydrolite drought validate output/drought_model
```

Meteorological, agricultural, hydrological, reservoir, groundwater, and composite drought are reported separately. Baseline period, time scale, distribution, freshness, and missing sources remain visible. Synthetic demos and user scenarios are not weather forecasts; diagnostic classes are not statutory warnings.

Raw user inputs remain immutable. Standardized or corrected copies belong in `standardized/` or `derived/`. The Cloud app is for lightweight demos and prepared outputs; local mode is recommended for long records and optional connectors.
