"""Shared status vocabulary for method-lab extensions.

The existing registries keep string values for backward compatibility.  New
experimental modules should use these values instead of inventing new labels.
"""

from enum import Enum


class _TextEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ExperimentStatus(_TextEnum):
    PLANNED = "planned"
    PARTIAL = "partial"
    EXPERIMENTAL = "experimental"
    AVAILABLE = "available"
    UNAVAILABLE_OPTIONAL = "unavailable_optional"
    BLOCKED = "blocked"


class MethodStatus(_TextEnum):
    LITERATURE_REFERENCE_ONLY = "literature_reference_only"
    METHOD_INSPIRED_CLEAN_ROOM = "method_inspired_clean_room"
    INTERFACE_ONLY = "interface_only"
    INDEPENDENT_ALGORITHM = "independent_algorithm"
    PROHIBITED_REUSE = "prohibited_reuse"
    SOURCE_INCOMPLETE = "source_incomplete"


def is_experiment_status(value: str) -> bool:
    return value in {item.value for item in ExperimentStatus}


def is_method_status(value: str) -> bool:
    return value in {item.value for item in MethodStatus}
