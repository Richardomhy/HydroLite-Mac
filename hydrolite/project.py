from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import zipfile
from typing import Any

import pandas as pd
import yaml

from hydrolite.batch import run_batch
from hydrolite.compare import run_compare
from hydrolite.config import load_case
from hydrolite.runner import run_case
from hydrolite.validate import validate_target


PROJECT_REQUIRED_DIRS = ["cases", "configs", "data", "output", "reports", "logs"]
PACKAGE_EXCLUDES = (
    ".streamlit/secrets.toml",
    "external/",
    ".venv/",
    "env/",
    "__pycache__/",
)
MODEL_WEIGHT_SUFFIXES = {".pt", ".pth", ".ckpt", ".onnx"}


def _project_path(project_dir: str | Path) -> Path:
    return Path(project_dir).expanduser().resolve()


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _default_project_yaml(project_dir: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "project_name": "Demo HydroLite Project",
        "project_id": "demo_project",
        "created_at": now,
        "description": "Demo project wrapping HydroLite, GEE, SWMM, and OpenHydroNet-ready workflows.",
        "author": "HydroLite-Mac",
        "version": "0.1",
        "paths": {
            "cases_dir": "cases",
            "configs_dir": "configs",
            "data_dir": "data",
            "output_dir": "output",
            "reports_dir": "reports",
            "logs_dir": "logs",
        },
        "modules": {
            "hydrolite": True,
            "swmm": True,
            "gee": True,
            "openhydronet": True,
        },
        "default_cases": ["demo.yaml", "demo_gee.yaml", "demo_swmm.yaml"],
        "gee": {"project_env_var": "GEE_PROJECT"},
        "notes": [
            "Project cases reference root demo inputs via relative paths.",
            "data_raw is never copied into the project package.",
            "OpenHydroNet external repositories and model weights are excluded.",
        ],
    }


def _project_case_yaml(case_name: str) -> dict[str, Any]:
    if case_name == "demo.yaml":
        return {
            "name": "demo",
            "model": {"time_step_hours": 1.0},
            "inputs": {
                "directory": "../../data_demo",
                "rainfall": "rainfall.csv",
                "subcatchments": "subcatchments.csv",
                "reaches": "reaches.csv",
            },
            "outputs": {"directory": "output/demo"},
        }
    if case_name == "demo_gee.yaml":
        return {
            "name": "demo_gee",
            "model": {"time_step_hours": 24.0},
            "inputs": {
                "directory": "../..",
                "rainfall": "output/gee/hydrolite_inputs/gee_chirps_rainfall.csv",
                "subcatchments": "data_demo/gee/gee_subbasins.csv",
                "reaches": "data_demo/gee/gee_reaches.csv",
            },
            "outputs": {"directory": "output/demo_gee"},
            "observed": {
                "enabled": True,
                "observed_streamflow_csv": "../../data_demo/observed/demo_observed_streamflow.csv",
                "time_column": "datetime",
                "flow_column": "observed_streamflow_m3s",
                "gauge_id_column": "gauge_id",
            },
        }
    if case_name == "demo_swmm.yaml":
        return {
            "name": "demo_swmm",
            "model": {"time_step_hours": 1.0},
            "inputs": {
                "directory": "../../data_demo",
                "rainfall": "rainfall.csv",
                "subcatchments": "subcatchments.csv",
                "reaches": "reaches.csv",
            },
            "outputs": {"directory": "output/demo_swmm"},
            "swmm": {
                "enabled": True,
                "inp_file": "../../data_raw/swmm/demo.inp",
                "coupling": {
                    "enabled": True,
                    "source_flow_csv": "output/demo_swmm/result_flow.csv",
                    "source_time_column": "time",
                    "source_flow_column": "outflow_cms",
                    "target_node": "J1",
                    "inflow_name": "HYDROLITE_INFLOW",
                    "flow_unit": "CMS",
                },
            },
        }
    raise ValueError(f"Unknown demo case template: {case_name}")


def _copy_demo_configs(project_dir: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    configs_dir = project_dir / "configs"
    for name in ("gee.example.yaml", "openhydronet.example.yaml"):
        source = root / "configs" / name
        if source.exists():
            shutil.copy2(source, configs_dir / name)


def create_project(project_dir: str | Path, template: str = "demo") -> Path:
    project = _project_path(project_dir)
    if project.exists() and any(project.iterdir()):
        raise FileExistsError(f"Project already exists and is not empty: {project}")
    for directory in PROJECT_REQUIRED_DIRS:
        (project / directory).mkdir(parents=True, exist_ok=True)
    data_readme = project / "data" / "README.md"
    data_readme.write_text(
        "# Project Data\n\nThis demo project references root `data_demo/` files instead of copying raw data.\n",
        encoding="utf-8",
    )
    config = _default_project_yaml(project)
    _write_yaml(project / "project.yaml", config)
    if template == "demo":
        for case_name in config["default_cases"]:
            _write_yaml(project / "cases" / case_name, _project_case_yaml(case_name))
        _copy_demo_configs(project)
    return write_project_summary(project)


def load_project(project_dir: str | Path) -> dict[str, Any]:
    project = _project_path(project_dir)
    config_path = project / "project.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"project.yaml not found: {config_path}")
    data = _read_yaml(config_path)
    data["_project_dir"] = str(project)
    return data


def _resolve_project_path(project_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (project_dir / path).resolve()


def _project_dirs(project_dir: Path, project: dict[str, Any]) -> dict[str, Path]:
    paths = project.get("paths") or {}
    return {
        key: _resolve_project_path(project_dir, str(paths.get(key, key.replace("_dir", ""))))
        for key in ("cases_dir", "configs_dir", "data_dir", "output_dir", "reports_dir", "logs_dir")
    }


def list_project_cases(project_dir: str | Path) -> list[Path]:
    project_path = _project_path(project_dir)
    project = load_project(project_path)
    cases_dir = _project_dirs(project_path, project)["cases_dir"]
    return sorted([*cases_dir.glob("*.yaml"), *cases_dir.glob("*.yml")])


def validate_project(project_dir: str | Path) -> dict[str, Path | pd.DataFrame]:
    project_path = _project_path(project_dir)
    project = load_project(project_path)
    dirs = _project_dirs(project_path, project)
    rows: list[dict[str, Any]] = []
    for key, path in dirs.items():
        status = "passed" if path.exists() else "failed"
        rows.append({"check_group": "directories", "check_name": key, "status": status, "message": str(path)})
    validation = validate_target(dirs["cases_dir"])
    reports_dir = dirs["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    xlsx = reports_dir / "project_validation.xlsx"
    report_md = reports_dir / "project_validation_report.md"
    project_checks = pd.DataFrame(rows)
    with pd.ExcelWriter(xlsx) as writer:
        project_checks.to_excel(writer, sheet_name="project_checks", index=False)
        validation.overview.to_excel(writer, sheet_name="case_overview", index=False)
        validation.checks.to_excel(writer, sheet_name="case_checks", index=False)
        validation.errors.to_excel(writer, sheet_name="case_errors", index=False)
        validation.warnings.to_excel(writer, sheet_name="case_warnings", index=False)
    report_md.write_text(
        "\n".join(
            [
                "# Project Validation Report",
                "",
                f"Project: `{project.get('project_name', project_path.name)}`",
                f"Project directory: `{project_path}`",
                f"Fatal case errors: `{len(validation.errors)}`",
                f"Case warnings: `{len(validation.warnings)}`",
                f"Case validation workbook: `{validation.outputs.xlsx}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"xlsx": xlsx, "report_md": report_md, "project_checks": project_checks, "case_validation_xlsx": validation.outputs.xlsx}


def run_project_case(project_dir: str | Path, case_name: str) -> Any:
    project_path = _project_path(project_dir)
    project = load_project(project_path)
    dirs = _project_dirs(project_path, project)
    case_file = dirs["cases_dir"] / case_name
    if not case_file.exists():
        raise FileNotFoundError(f"Project case not found: {case_file}")
    config = load_case(case_file)
    output_dir = dirs["output_dir"] / config.name
    return run_case(case_file, output_dir=output_dir)


def run_project_batch(project_dir: str | Path) -> tuple[Path, list[dict[str, object]], list[str]]:
    project_path = _project_path(project_dir)
    project = load_project(project_path)
    cases_dir = _project_dirs(project_path, project)["cases_dir"]
    return run_batch(cases_dir)


def compare_project_outputs(project_dir: str | Path) -> Any:
    project_path = _project_path(project_dir)
    project = load_project(project_path)
    output_dir = _project_dirs(project_path, project)["output_dir"]
    return run_compare(output_dir)


def _safe_package_member(path: Path) -> bool:
    text = path.as_posix()
    if any(part in text for part in PACKAGE_EXCLUDES):
        return False
    if path.suffix.lower() in MODEL_WEIGHT_SUFFIXES:
        return False
    if path.name == ".DS_Store" or path.suffix == ".pyc":
        return False
    if path.suffix == ".zip":
        return False
    return True


def export_project_package(project_dir: str | Path) -> Path:
    project_path = _project_path(project_dir)
    project = load_project(project_path)
    dirs = _project_dirs(project_path, project)
    reports_dir = dirs["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    package = reports_dir / f"{project.get('project_id', project_path.name)}_package.zip"
    include_roots = [
        project_path / "project.yaml",
        dirs["cases_dir"],
        dirs["configs_dir"],
        dirs["output_dir"] / "comparison",
        dirs["reports_dir"],
        project_path / "project_summary.md",
    ]
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root in include_roots:
            if not root.exists():
                continue
            if root.is_file():
                if _safe_package_member(root):
                    archive.write(root, root.relative_to(project_path))
                continue
            for path in root.rglob("*"):
                if path.is_file() and _safe_package_member(path):
                    archive.write(path, path.relative_to(project_path))
    return package


def write_project_summary(project_dir: str | Path) -> Path:
    project_path = _project_path(project_dir)
    project = load_project(project_path) if (project_path / "project.yaml").exists() else _default_project_yaml(project_path)
    dirs = _project_dirs(project_path, project)
    cases = [path.name for path in list_project_cases(project_path)] if (project_path / "project.yaml").exists() else []
    output_files = sorted(str(path.relative_to(project_path)) for path in dirs["output_dir"].rglob("*") if path.is_file()) if dirs["output_dir"].exists() else []
    path = project_path / "project_summary.md"
    path.write_text(
        "\n".join(
            [
                "# HydroLite Project Summary",
                "",
                f"Project name: `{project.get('project_name', '')}`",
                f"Project ID: `{project.get('project_id', '')}`",
                f"Description: {project.get('description', '')}",
                "",
                "## Modules",
                "",
                *[f"- {name}: `{enabled}`" for name, enabled in (project.get("modules") or {}).items()],
                "",
                "## Cases",
                "",
                *[f"- `{case}`" for case in cases],
                "",
                "## Outputs",
                "",
                *[f"- `{item}`" for item in output_files[:100]],
                "",
                "## Next Steps",
                "",
                "- Validate project cases.",
                "- Run project scenarios.",
                "- Compare project outputs.",
                "- Export a project package for sharing.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def project_info(project_dir: str | Path) -> dict[str, Any]:
    project_path = _project_path(project_dir)
    project = load_project(project_path)
    dirs = _project_dirs(project_path, project)
    return {
        "project": project,
        "directories": {key: str(value) for key, value in dirs.items()},
        "cases": [path.name for path in list_project_cases(project_path)],
    }
