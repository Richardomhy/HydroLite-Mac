from __future__ import annotations

from hydrolite.app_settings import load_settings, save_settings


DESKTOP_DEFAULTS = {
    "check_updates_on_start": False,
    "recover_interrupted_runs_on_start": True,
    "open_last_project": False,
    "theme": "system",
}


def load_desktop_settings() -> dict:
    return {**DESKTOP_DEFAULTS, **load_settings()}


def save_desktop_settings(settings: dict):
    safe = {**load_desktop_settings(), **settings}
    if safe.get("theme") not in {"system", "light", "dark"}:
        raise ValueError("theme must be system, light, or dark")
    return save_settings(safe)
