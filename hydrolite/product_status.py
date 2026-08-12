"""Product-facing status service built from existing registries and evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from hydrolite.capability_registry import get_capability, list_capabilities


VALIDATION_LEVELS = ("synthetic_demo", "framework_ready", "ready_with_warnings", "real_data_tested", "independently_validated", "production_ready")


@dataclass(frozen=True, slots=True)
class ProductFeatureStatus:
    feature_id: str
    status: str
    validation_level: str
    data_readiness: str
    dependency_status: str
    environment_status: str
    warning_count: int
    limitations: tuple[str, ...]
    recommended_action: str
    real_data_tested: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_EVIDENCE = {
    "gamma_lag_features": ("synthetic_demo", ("Synthetic value-added demonstrated; real value-added not tested.",)),
    "river_graph_features": ("synthetic_demo", ("Graph synthetic value-added demonstrated; real value-added not tested.",)),
    "trend_aware_features": ("synthetic_demo", ("Trend synthetic value-added not demonstrated; do not recommend by default.",)),
    "multihorizon_forecast": ("synthetic_demo", ("Long-horizon skill must be checked per horizon on real data.",)),
    "water_quality_method_lab": ("synthetic_demo", ("Hydrology 12/16, Graph 13/16, Gamma 1/16, Trend 0/16; overall mixed; real data not tested.",)),
    "flood_susceptibility": ("synthetic_demo", ("Logistic selected; complex-model value-added not demonstrated; susceptibility is not risk.",)),
    "flood_susceptibility_xai": ("synthetic_demo", ("XAI importance stability is unstable; RL suitability is rl_not_justified; real data not tested.",)),
    "water_quality": ("framework_ready", ("Production water-quality simulation remains planned.",)),
    "water_quality_data_analysis": ("ready_with_warnings", ("Observation analysis is available; it is not a pollutant process simulation.",)),
    "flood_forecast": ("ready_with_warnings", ("Partial capability; not a production warning service.",)),
    "drought_forecast": ("ready_with_warnings", ("Partial capability; validate forcing and horizon skill.",)),
    "hydrology": ("production_ready", ("Project-specific data validation and calibration remain required.",)),
}


def get_product_feature_status(feature_id: str, *, data_readiness: str = "unknown", dependency_status: str = "available", environment_status: str = "available") -> ProductFeatureStatus:
    capability = get_capability(feature_id)
    validation, limitations = _EVIDENCE.get(feature_id, ("framework_ready", ()))
    status = capability["status"]
    if status == "planned": product_status = "planned"
    elif status.startswith("unavailable"): product_status = "unavailable"
    elif validation == "synthetic_demo": product_status = "experimental"
    elif status == "available" and validation == "production_ready": product_status = "production_ready"
    else: product_status = "ready_with_warnings"
    warnings = len(limitations) + int(data_readiness not in {"ready", "unknown"}) + int(dependency_status != "available") + int(environment_status != "available")
    action = "可进入场景配置。" if not warnings else "请先查看限制、数据就绪度和依赖状态。"
    return ProductFeatureStatus(feature_id, product_status, validation, data_readiness, dependency_status, environment_status, warnings, tuple(limitations), action, False)


def list_product_feature_statuses() -> list[dict[str, Any]]:
    return [get_product_feature_status(item["capability_id"]).as_dict() for item in list_capabilities()]


def product_status_summary() -> dict[str, Any]:
    rows = list_product_feature_statuses()
    return {
        "status": "passed",
        "feature_count": len(rows),
        "features": rows,
        "validation_levels": list(VALIDATION_LEVELS),
        "rule": "Runnable does not imply real-data tested or production ready.",
    }
