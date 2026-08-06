from __future__ import annotations

import numpy as np
import pandas as pd

CONDITIONING_FACTORS = ["dem", "slope", "aspect", "curvature", "flow_accumulation", "flow_direction", "topographic_wetness", "distance_to_stream", "distance_to_road", "distance_to_settlement", "rainfall_extreme", "land_use", "ndvi", "soil", "geology", "imperviousness", "drought_state", "hydrolite_runoff"]


def build_synthetic_flood_features(rows=120, seed=7):
    rng=np.random.default_rng(seed); frame=pd.DataFrame({name:rng.normal(size=rows) for name in CONDITIONING_FACTORS}); frame["spatial_block"] = np.arange(rows) % 6; frame["x"] = np.arange(rows) % 20; frame["y"] = np.arange(rows) // 20
    score=1.4*frame.rainfall_extreme + .9*frame.hydrolite_runoff - .8*frame.distance_to_stream + rng.normal(scale=.8,size=rows); frame["flood"]=(score>np.quantile(score,.7)).astype(int); return frame


def build_conditioning_features(workspace):
    return {"status":"passed", "workspace":str(workspace), "factors":CONDITIONING_FACTORS, "factor_count":len(CONDITIONING_FACTORS), "synthetic_demo":True}
