from __future__ import annotations

from pathlib import Path
import logging
import re

from hydrolite.runtime_db import create_log_record, list_log_records
from hydrolite.runtime_paths import get_run_log_dir


SENSITIVE = (
    re.compile(r"(?i)(token|password|api[_-]?key|authorization|cookie|client_secret)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)(username\s*[:=]\s*\S+\s+password\s*[:=]\s*)(\S+)"),
)


def redact_sensitive_values(message: object) -> str:
    text = str(message)
    for pattern in SENSITIVE:
        text = pattern.sub(r"\1=[REDACTED]", text)
    return text


def sanitize_log_message(message: object) -> str:
    return redact_sensitive_values(message).replace("\x00", "")[:10000]


def configure_runtime_logging(runtime_dir: str | Path) -> logging.Logger:
    root = Path(runtime_dir)
    root.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("hydrolite.runtime")
    logger.setLevel(logging.INFO)
    if not any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == root / "runtime.log" for handler in logger.handlers):
        handler = logging.FileHandler(root / "runtime.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def get_run_logger(run_id: str) -> logging.Logger:
    return configure_runtime_logging(get_run_log_dir(run_id))


def get_task_logger(task_id: str) -> logging.Logger:
    return logging.getLogger(f"hydrolite.runtime.task.{task_id}")


def log_runtime_event(run_id: str, task_id: str | None, level: str, message: object) -> int:
    clean = sanitize_log_message(message)
    get_run_logger(run_id).log(getattr(logging, level.upper(), logging.INFO), clean)
    return create_log_record(run_id, task_id, level.upper(), clean)


def read_task_log(task_id: str, limit: int | None = None) -> list[dict]:
    rows = list_log_records(task_id=task_id)
    return rows[-limit:] if limit else rows


def search_logs(run_id: str, query: str) -> list[dict]:
    needle = query.casefold()
    return [row for row in list_log_records(run_id=run_id) if needle in row["message"].casefold()]


def summarize_run_logs(run_id: str) -> dict:
    rows = list_log_records(run_id=run_id)
    counts = {level: sum(row["level"] == level for row in rows) for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")}
    return {"run_id": run_id, "count": len(rows), "levels": counts}


def write_log_summary(run_id: str, output_dir: str | Path) -> Path:
    path = Path(output_dir) / "run_log_summary.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize_run_logs(run_id)
    path.write_text("# Run Log Summary\n\n" + "\n".join(f"- {key}: `{value}`" for key, value in summary["levels"].items()) + "\n", encoding="utf-8")
    return path
