from __future__ import annotations

from pathlib import Path
from typing import Any

from hydrolite.__version__ import __app_name__, __release_date__, __version__
from hydrolite.healthcheck import build_healthcheck, healthcheck_status


GITHUB_URL = "https://github.com/Richardomhy/HydroLite-Mac.git"
STREAMLIT_URL = "https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app"
RELEASE_TAG = "v0.6.0-beta.1"
ALPHA_TAG = "v0.5.0-alpha.2"


def beta_info(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root).resolve()
    return {
        "app_name": __app_name__,
        "version": __version__,
        "release_date": __release_date__,
        "github_url": GITHUB_URL,
        "streamlit_url": STREAMLIT_URL,
        "release_tag": RELEASE_TAG,
        "docs": {
            "post_release_validation": str(root / "docs" / "post_release_validation.md"),
            "cloud_smoke_test": str(root / "docs" / "cloud_smoke_test.md"),
            "local_smoke_test": str(root / "docs" / "local_smoke_test.md"),
            "beta_feedback_workflow": str(root / "docs" / "beta_feedback_workflow.md"),
            "beta_user_feedback": str(root / "docs" / "beta_user_feedback.md"),
        },
    }


def beta_checklist() -> list[dict[str, str]]:
    return [
        {"area": "GitHub Release", "check": "Confirm v0.6.0-beta.1 tag and release assets are visible."},
        {"area": "Release assets", "check": "Download release notes, demo package, report bundle, and data template bundle."},
        {"area": "Streamlit Cloud", "check": "Open online URL and confirm the workbench loads."},
        {"area": "Home page", "check": "Confirm version, beta feedback entry, and safety notes are visible."},
        {"area": "Tutorial", "check": "Open 教程与 Demo and complete the guided checklist review."},
        {"area": "Data templates", "check": "Download templates and validate templates/data/examples."},
        {"area": "Project wizard", "check": "Preview basic wizard template."},
        {"area": "Reports", "check": "Open report export page and confirm report downloads are available."},
        {"area": "No secrets", "check": "Do not upload credentials, tokens, API keys, private data, or model weights."},
        {"area": "Issue tracking", "check": "Use GitHub Issue templates for bugs, feature requests, beta feedback, and data template issues."},
    ]


def beta_smoke_local(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root).resolve()
    health = build_healthcheck()
    return {
        "version": __version__,
        "healthcheck_status": healthcheck_status(health),
        "healthcheck_report": str(health.report_md),
        "readme_exists": (root / "README.md").exists(),
        "release_dir_exists": (root / "release" / "v0.6.0-beta.1").exists(),
        "streamlit_app_exists": (root / "streamlit_app.py").exists(),
    }
