from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def load_openhydronet_predictions_placeholder(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
    return pd.DataFrame(columns=["datetime", "basin_id", "forecast_flow", "status"])


def write_openhydronet_summary_placeholder(path: str | Path, summary: dict[str, Any] | None = None) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = summary or {
        "run_status": "placeholder",
        "message": "OpenHydroNet postprocessing is not implemented yet.",
    }
    pd.DataFrame([payload]).to_excel(output_path, index=False)
    return output_path
