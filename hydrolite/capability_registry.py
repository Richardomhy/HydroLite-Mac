from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


_CAPABILITIES = {
    "watershed_delineation": "partial",
    "hydrology": "available",
    "flood_forecast": "partial",
    "drought_forecast": "planned",
    "reservoir_routing": "partial",
    "hec_hms": "partial",
    "swmm": "partial",
    "icesat2": "partial",
    "rusle": "partial",
    "sediment_delivery": "partial",
    "conservation": "partial",
    "watershed_accounting": "partial",
    "water_quality": "planned",
    "machine_learning": "partial",
    "deep_learning": "unavailable_optional",
}


def list_capabilities() -> list[dict[str, str]]:
    return [
        {
            "capability_id": name,
            "status": status,
            "description_zh": f"{name} 当前状态：{status}",
            "description_en": f"{name} current status: {status}",
        }
        for name, status in _CAPABILITIES.items()
    ]


def get_capability(capability_id: str) -> dict[str, str]:
    return next(row for row in list_capabilities() if row["capability_id"] == capability_id)


def write_capability_registry(output_dir: str | Path) -> dict[str, Path]:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = list_capabilities()
    xlsx = root / "platform_capability_matrix.xlsx"
    json_path = root / "platform_capability_matrix.json"
    report = root / "platform_capability_matrix.md"
    pd.DataFrame(rows).to_excel(xlsx, index=False)
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    report.write_text("# Platform capability matrix\n\n```text\n" + pd.DataFrame(rows)[["capability_id", "status"]].to_string(index=False) + "\n```\n", encoding="utf-8")
    return {"xlsx": xlsx, "json": json_path, "report": report}
