from __future__ import annotations

import pandas as pd
from pathlib import Path

VARIABLES = ["CODMn", "NH3-N", "TN", "TP", "DO", "temperature", "turbidity", "conductivity", "pH"]
MODES = ["station_independent_baseline", "upstream_weighted_baseline", "graph_feature_regression", "trend_graph_regression", "causal_graph_temporal", "hierarchical_multihorizon"]


def assess_water_quality_experiment(data=None):
    return {"water_quality": "planned", "water_quality_method_lab": "partial", "validation_level": "synthetic_method_demo" if data is None else "requires_real_multistation_validation", "variables": VARIABLES, "modes": MODES}


def station_independent_baseline(frame, value_column):
    data=pd.DataFrame(frame).copy(); data["prediction"] = data.groupby("station_id")[value_column].shift(1); return data


def write_water_quality_method_demo(output_dir="output/method_inspiration"):
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True); dates=pd.date_range("2020-01-01",periods=20); rows=[]
    for station in [f"W{i}" for i in range(1,8)]:
        for day,date in enumerate(dates): rows.append({"timestamp":date,"station_id":station,"CODMn":3+day*.02,"NH3-N":.1+day*.001,"TN":1.2,"TP":.08,"horizon_days": [1,3,7,14][day%4],"prediction":3+max(day-1,0)*.02,"synthetic_demo":True})
    frame=pd.DataFrame(rows); frame.to_csv(root/"station_forecasts.csv",index=False); pd.DataFrame([{ "horizon_days":h,"rmse":.1+h*.01,"validation_level":"synthetic_method_demo"} for h in (1,3,7,14)]).to_excel(root/"multihorizon_metrics.xlsx",index=False); (root/"water_quality_method_report.md").write_text("# Water-quality method interface\n\nSynthetic method demo only. Production water_quality remains planned.\n",encoding="utf-8"); return {"status":"passed","validation_level":"synthetic_method_demo","forecast":root/"station_forecasts.csv"}
