from __future__ import annotations

import socket
from urllib.parse import urlparse


_RESERVATIONS: dict[int, socket.socket] = {}


def reserve_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    _RESERVATIONS[port] = sock
    return port


def release_port(port: int) -> None:
    sock = _RESERVATIONS.pop(int(port), None)
    if sock:
        sock.close()


def find_free_loopback_port() -> int:
    port = reserve_port()
    release_port(port)
    return port


def reject_non_loopback_address(address: str) -> None:
    if address not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError(f"Desktop backend must use a loopback address, not {address!r}")


def validate_loopback_url(url: str) -> bool:
    parsed = urlparse(url)
    reject_non_loopback_address(parsed.hostname or "")
    if parsed.scheme != "http" or not parsed.port:
        raise ValueError("Desktop URL must be an HTTP loopback URL with an explicit port")
    return True
