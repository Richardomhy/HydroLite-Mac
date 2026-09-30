"""Bounded public HTTPS only. Never execute data, follow private redirects or log credentials."""
from contextlib import contextmanager
import ipaddress
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qsl
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ConnectorError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def validate_public_url(url, allowed_hosts):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in {None, 443} or parts.hostname not in allowed_hosts:
        raise ConnectorError("unsafe_url", "Only configured public HTTPS hosts are allowed")
    if any(any(word in key.lower() for word in ("token", "key", "secret", "credential", "signature")) for key, _ in parse_qsl(parts.query)):
        raise ConnectorError("unsafe_url", "Credential-bearing URLs cannot be cached")
    try:
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ConnectorError("online_source_unavailable", "Public host DNS unavailable") from exc
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ConnectorError("unsafe_url", "Private, loopback and metadata service addresses are forbidden")
    return url


class PublicRedirect(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@contextmanager
def open_public(url, hosts, headers=None, interval=0, attempts=3):
    validate_public_url(url, hosts)
    opener = build_opener(PublicRedirect(hosts))
    response = None
    for attempt in range(min(attempts, 3)):
        try:
            time.sleep(max(0, min(float(interval), 10)))
            response = opener.open(Request(url, headers={"User-Agent": "HydroLite-DataHub/1", **(headers or {})}), timeout=15)
            break
        except HTTPError as exc:
            if exc.code == 304:
                response = exc
                break
            status = "authentication_required" if exc.code in {401, 403} else "rate_limited" if exc.code == 429 else "online_source_unavailable"
            delay = exc.headers.get("Retry-After", "")
            if attempt == min(attempts, 3) - 1 or exc.code not in {429, 500, 502, 503, 504}:
                raise ConnectorError(status, f"Provider HTTP {exc.code}") from exc
            # Long Retry-After is reported, never retried earlier than requested.
            if delay and (not delay.isdigit() or int(delay) > 10):
                raise ConnectorError(status, "Provider requests delayed retry; try again later") from exc
            time.sleep(max(float(delay or 0), 2 ** attempt))
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == min(attempts, 3) - 1:
                raise ConnectorError("online_source_unavailable", "Provider network request failed") from exc
            time.sleep(2 ** attempt)
    try:
        yield response
    finally:
        if response:
            response.close()
