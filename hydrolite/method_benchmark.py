from __future__ import annotations

from pathlib import Path
import pandas as pd


def evaluate_method_value_added(scores: dict[str, float], baseline: str) -> dict:
    best = max(scores, key=scores.get) if scores else None
    return {"baseline": baseline, "best": best, "method_value_added": "demonstrated" if best and best != baseline and scores[best] > scores.get(baseline, float("-inf")) else "not_demonstrated"}


def write_method_benchmark(output_dir="output/method_inspiration"):
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True)
    rows=[{"method":"raw_lag","score":.42},{"method":"rolling_rainfall","score":.48},{"method":"linear_reservoir","score":.54},{"method":"hydrolite_physical","score":.55},{"method":"hydrolite_gamma_features","score":.57}]; frame=pd.DataFrame(rows); frame.to_excel(root/"method_benchmark.xlsx",index=False); result=evaluate_method_value_added(dict(zip(frame.method,frame.score)),"hydrolite_physical"); (root/"method_benchmark_report.md").write_text("# Method benchmark\n\n"+str(result)+"\nSynthetic method demo only.\n",encoding="utf-8"); return {"status":"passed",**result,"output":root/"method_benchmark.xlsx"}
