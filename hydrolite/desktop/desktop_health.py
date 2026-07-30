from __future__ import annotations

import socket
import urllib.request

from hydrolite.desktop.port_manager import validate_loopback_url
from hydrolite.runtime_db import get_database_version


def check_tcp_port(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def check_http_endpoint(url: str, timeout: float = 2.0) -> bool:
    validate_loopback_url(url)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400
    except OSError:
        return False


def check_desktop_health(port: int, process_running: bool = True) -> dict:
    base = f"http://127.0.0.1:{int(port)}"
    tcp = check_tcp_port(port)
    health = check_http_endpoint(f"{base}/_stcore/health") if tcp else False
    page = check_http_endpoint(base) if health else False
    try:
        database = get_database_version() >= 1
    except Exception:
        database = False
    passed = process_running and tcp and health and page and database
    return {"status": "passed" if passed else "failed", "process_running": process_running, "tcp": tcp, "health_endpoint": health, "page": page, "database": database, "url": base}
