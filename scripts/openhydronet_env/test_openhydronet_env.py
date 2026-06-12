from __future__ import annotations

from pathlib import Path
import importlib
import json
import os
import platform
import sys
import traceback


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = PROJECT_ROOT / "output" / "openhydronet_env" / "test_env_report.txt"


def _repo_path() -> Path:
    return Path(os.environ.get("OPENHYDRONET_HOME") or PROJECT_ROOT / "external" / "openhydronet" / "flood-forecasting").expanduser()


def _torch_info() -> dict[str, object]:
    try:
        import torch

        return {
            "installed": True,
            "version": getattr(torch, "__version__", ""),
            "mps_available": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
            "cuda_available": bool(torch.cuda.is_available()),
        }
    except Exception as exc:
        return {"installed": False, "version": "", "mps_available": False, "cuda_available": False, "error": str(exc)}


def _try_import_repo(repo: Path) -> dict[str, object]:
    result: dict[str, object] = {"can_import": False, "imported_module": "", "error": "", "sys_path": []}
    if not repo.exists():
        result["error"] = f"Repository path does not exist: {repo}"
        result["sys_path"] = sys.path
        return result
    sys.path.insert(0, str(repo))
    candidates = ["googlehydrology", "flood_forecasting", "hydrology", "models"]
    for name in candidates:
        try:
            importlib.import_module(name)
            result["can_import"] = True
            result["imported_module"] = name
            break
        except Exception as exc:
            result["error"] += f"{name}: {exc}\n"
    result["sys_path"] = sys.path
    return result


def build_report() -> dict[str, object]:
    repo = _repo_path()
    torch = _torch_info()
    import_result = _try_import_repo(repo)
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform_machine": platform.machine(),
        "torch_version": torch.get("version", ""),
        "mps_available": torch.get("mps_available", False),
        "cuda_available": torch.get("cuda_available", False),
        "OPENHYDRONET_HOME": os.environ.get("OPENHYDRONET_HOME", ""),
        "repo_path": str(repo),
        "repo_exists": repo.exists(),
        "readme_exists": any((repo / name).exists() for name in ("README.md", "README.rst", "README")),
        "requirements_exists": (repo / "requirements.txt").exists(),
        "import_result": import_result,
    }


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = build_report()
    except Exception as exc:
        report = {"status": "failed", "error": str(exc), "traceback": traceback.format_exc()}
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote OpenHydroNet environment test report to: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

