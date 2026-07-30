from __future__ import annotations

from pathlib import Path
import logging

from hydrolite.desktop.desktop_paths import get_desktop_log_dir
from hydrolite.runtime_logging import sanitize_log_message


def configure_desktop_logging(log_dir: str | Path | None = None) -> logging.Logger:
    root = Path(log_dir or get_desktop_log_dir())
    root.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("hydrolite.desktop")
    logger.setLevel(logging.INFO)
    target = root / "desktop.log"
    if not any(isinstance(item, logging.FileHandler) and Path(item.baseFilename) == target for item in logger.handlers):
        handler = logging.FileHandler(target, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def log_desktop_event(level: str, message: object) -> None:
    configure_desktop_logging().log(getattr(logging, level.upper(), logging.INFO), sanitize_log_message(message))
