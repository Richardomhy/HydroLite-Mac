from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import importlib.metadata
import os
import platform
import subprocess
import sys
from typing import Any

from hydrolite.gee.auth import get_gee_status
from hydrolite.openhydronet.runner import detect_openhydronet_environment
from hydrolite.project import project_info


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = PROJECT_ROOT / "cases"
OUTPUT_ROOT = PROJECT_ROOT / "output"
PROJECTS_ROOT = PROJECT_ROOT / "projects"
DEFAULT_PROJECT = PROJECTS_ROOT / "demo_project"


@dataclass(frozen=True)
class WorkbenchContext:
    project_dir: Path
    project_exists: bool
    project_loaded: bool
    project: dict[str, Any]
    project_name: str
    project_id: str
    directories: dict[str, str]
    cases: list[str]
    is_cloud: bool
    swmm_python_detected: bool
    swmm_python: str
    gee_project_detected: bool
    gee_project: str
    gee_status: dict[str, Any]
    openhydronet_status: dict[str, Any]
    error_message: str


def is_streamlit_cloud() -> bool:
    markers = (
        "STREAMLIT_CLOUD",
        "STREAMLIT_COMMUNITY_CLOUD",
        "STREAMLIT_SHARING_MODE",
        "STREAMLIT_RUNTIME_ENV",
    )
    return any(os.environ.get(name) for name in markers)


def swmm_python_status() -> tuple[bool, str]:
    value = os.environ.get("HYDROLITE_SWMM_PYTHON", "")
    if not value:
        return False, ""
    path = Path(value).expanduser()
    return path.exists(), str(path)


def gee_project_status() -> tuple[bool, str]:
    value = os.environ.get("GEE_PROJECT", "")
    return bool(value), value


def scan_case_files(cases_dir: str | Path = CASES_DIR) -> list[Path]:
    root = Path(cases_dir)
    if not root.exists():
        return []
    return sorted([*root.glob("*.yaml"), *root.glob("*.yml")])


def scan_project_dirs(projects_dir: str | Path = PROJECTS_ROOT) -> list[Path]:
    root = Path(projects_dir)
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "project.yaml").exists())


def get_git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return completed.stdout.strip() if completed.returncode == 0 else ""
    except Exception:
        return ""


def dependency_versions() -> dict[str, str]:
    packages = ["streamlit", "pandas", "numpy", "matplotlib", "openpyxl", "yaml", "scipy", "pyswmm", "swmm-toolkit"]
    versions = {"python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine()}
    for package in packages:
        distribution = "pyyaml" if package == "yaml" else package
        try:
            versions[package] = importlib.metadata.version(distribution)
        except Exception:
            versions[package] = "not installed"
    return versions


def load_workbench_context(project_dir: str | Path) -> WorkbenchContext:
    project_path = Path(project_dir).expanduser().resolve()
    has_swmm_python, swmm_python = swmm_python_status()
    has_gee_project, gee_project = gee_project_status()
    gee_status = get_gee_status()
    openhydronet_status = detect_openhydronet_environment()
    if not (project_path / "project.yaml").exists():
        return WorkbenchContext(
            project_dir=project_path,
            project_exists=project_path.exists(),
            project_loaded=False,
            project={},
            project_name="",
            project_id="",
            directories={},
            cases=[],
            is_cloud=is_streamlit_cloud(),
            swmm_python_detected=has_swmm_python,
            swmm_python=swmm_python,
            gee_project_detected=has_gee_project,
            gee_project=gee_project,
            gee_status=gee_status,
            openhydronet_status=openhydronet_status,
            error_message=f"project.yaml not found: {project_path / 'project.yaml'}",
        )
    try:
        info = project_info(project_path)
        project = info["project"]
        return WorkbenchContext(
            project_dir=project_path,
            project_exists=True,
            project_loaded=True,
            project=project,
            project_name=str(project.get("project_name") or project_path.name),
            project_id=str(project.get("project_id") or project_path.name),
            directories=dict(info.get("directories") or {}),
            cases=list(info.get("cases") or []),
            is_cloud=is_streamlit_cloud(),
            swmm_python_detected=has_swmm_python,
            swmm_python=swmm_python,
            gee_project_detected=has_gee_project,
            gee_project=gee_project,
            gee_status=gee_status,
            openhydronet_status=openhydronet_status,
            error_message="",
        )
    except Exception as exc:
        return WorkbenchContext(
            project_dir=project_path,
            project_exists=project_path.exists(),
            project_loaded=False,
            project={},
            project_name="",
            project_id="",
            directories={},
            cases=[],
            is_cloud=is_streamlit_cloud(),
            swmm_python_detected=has_swmm_python,
            swmm_python=swmm_python,
            gee_project_detected=has_gee_project,
            gee_project=gee_project,
            gee_status=gee_status,
            openhydronet_status=openhydronet_status,
            error_message=str(exc),
        )
