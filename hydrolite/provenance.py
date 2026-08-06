"""Small shared safety and provenance helpers for method-lab outputs."""

from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_PATHS = (ROOT / "data_raw", ROOT / "tmp_emergency_0722")
EXPERIMENT_OUTPUT_NAMES = frozenset(
    {"gee_catalog_intelligence", "research_methods", "method_inspiration", "flood_susceptibility"}
)


def is_protected_path(path: str | Path) -> bool:
    candidate = Path(path).expanduser().resolve()
    return any(candidate == protected or protected in candidate.parents for protected in PROTECTED_PATHS)


def experiment_output_path(name: str) -> Path:
    if name not in EXPERIMENT_OUTPUT_NAMES:
        raise ValueError(f"Unknown method-lab output: {name}")
    path = (ROOT / "output" / name).resolve()
    if is_protected_path(path):  # Defensive even though names are allowlisted.
        raise ValueError(f"Protected path cannot be used for output: {path}")
    return path


def build_provenance_record(
    source_ids: Iterable[str], *, synthetic_demo: bool, implementation_mode: str = "method_inspired_clean_room"
) -> dict[str, object]:
    """Return report metadata without reading or copying a third-party asset."""
    return {
        "source_ids": list(source_ids),
        "implementation_mode": implementation_mode,
        "synthetic_demo": synthetic_demo,
        "physical_water_balance_authoritative": True,
        "clean_room_notice": "Independent HydroLite implementation; not a paper-model reproduction.",
    }
