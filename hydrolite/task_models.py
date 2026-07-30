from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RetryPolicy:
    max_attempts: int = 1
    retryable_errors: list[str] = field(default_factory=lambda: ["timeout", "external_backend_failed"])


@dataclass
class ResourceLimits:
    timeout_seconds: int = 300
    estimated_storage_mb: float = 10
    max_memory_mb: float | None = None


@dataclass
class TaskDependency:
    task_id: str
    required: bool = True


@dataclass
class TaskSpec:
    stage_id: str
    display_name: str
    task_type: str = "subprocess"
    handler: str | None = None
    command: list[str] = field(default_factory=list)
    arguments: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    dependencies: list[TaskDependency] = field(default_factory=list)
    timeout: int = 300
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    expected_outputs: list[str] = field(default_factory=list)
    quality_checks: list[str] = field(default_factory=list)
    optional: bool = False
    local_only: bool = False
    cloud_supported: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskResult:
    status: str
    return_code: int | None = None
    outputs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    runtime_seconds: float = 0


@dataclass
class RunSpec:
    project_id: str
    workflow_id: str
    run_mode: str = "local_light"
    tasks: list[TaskSpec] = field(default_factory=list)


@dataclass
class RunResult:
    run_id: str
    status: str
    progress: float


@dataclass
class ArtifactSpec:
    artifact_type: str
    path: str
    display_name: str = ""


@dataclass
class RuntimeEvent:
    event_type: str
    status: str
    message: str = ""
