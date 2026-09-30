"""Bounded public HTTPS only. Never execute data, follow private redirects or log credentials."""
from contextlib import contextmanager
from enum import Enum
import ipaddress
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qsl
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class ConnectorError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class NetworkSecurityPolicy(str, Enum):
    PRODUCTION_PUBLIC_ONLY = "production_public_only"
    TEST_LOOPBACK_ALLOWED = "test_loopback_allowed"


def _resolved_addresses(hostname, port):
    try:
        return sorted({row[4][0].split("%", 1)[0] for row in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise ConnectorError("dns_failure", "Provider host DNS resolution failed") from exc


def validate_public_url(url, allowed_hosts, policy=NetworkSecurityPolicy.PRODUCTION_PUBLIC_ONLY):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    try:
        port = parts.port
    except ValueError as exc:
        raise ConnectorError("configuration_error", "Invalid provider URL port") from exc
    if host not in {str(item).lower().rstrip(".") for item in allowed_hosts} or parts.username or parts.password:
        raise ConnectorError("configuration_error", "Provider URL must use a configured host and contain no credentials")
    if policy == NetworkSecurityPolicy.TEST_LOOPBACK_ALLOWED:
        if parts.scheme not in {"http", "https"} or not port:
            raise ConnectorError("unsafe_url", "Test policy only permits explicit loopback URLs")
    elif policy == NetworkSecurityPolicy.PRODUCTION_PUBLIC_ONLY:
        if parts.scheme != "https" or port not in {None, 443}:
            raise ConnectorError("configuration_error", "Production providers must use HTTPS on port 443")
    else:
        raise ConnectorError("configuration_error", "Unknown network security policy")
    if any(any(word in key.lower() for word in ("token", "key", "secret", "credential", "signature")) for key, _ in parse_qsl(parts.query)):
        raise ConnectorError("unsafe_url", "Credential-bearing URLs cannot be cached")
    addresses = _resolved_addresses(host, port or 443)
    if not addresses:
        raise ConnectorError("dns_failure", "Provider host DNS returned no addresses")
    parsed = [ipaddress.ip_address(address) for address in addresses]
    if policy == NetworkSecurityPolicy.TEST_LOOPBACK_ALLOWED:
        if any(not item.is_loopback for item in parsed):
            raise ConnectorError("unsafe_url", "Test policy permits loopback addresses only")
    elif any(not item.is_global for item in parsed):
        raise ConnectorError("non_public_resolution", "Provider DNS resolved to a non-public address; connection blocked")
    return url


class PublicRedirect(HTTPRedirectHandler):
    def __init__(self, hosts, policy=NetworkSecurityPolicy.PRODUCTION_PUBLIC_ONLY, chain=None):
        self.hosts = hosts
        self.policy = policy
        self.chain = chain if chain is not None else []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl, self.hosts, self.policy)
        self.chain.append({"status": code, "from_host": urlsplit(req.full_url).hostname, "to_host": urlsplit(newurl).hostname})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _network_failure(exc):
    reason = getattr(exc, "reason", exc)
    text = str(reason).lower()
    if "proxy" in text or "tunnel" in text:
        return "proxy_blocked"
    if "ssl" in text or "certificate" in text or "tls" in text:
        return "tls_failure"
    if isinstance(reason, socket.gaierror) or "name or service not known" in text or "nodename nor servname" in text:
        return "dns_failure"
    return "remote_unavailable"


@contextmanager
def open_public(url, hosts, headers=None, interval=0, attempts=3, policy=NetworkSecurityPolicy.PRODUCTION_PUBLIC_ONLY):
    validate_public_url(url, hosts, policy)
    redirects = []
    handlers = [PublicRedirect(hosts, policy, redirects)]
    if policy == NetworkSecurityPolicy.TEST_LOOPBACK_ALLOWED:
        handlers.insert(0, ProxyHandler({}))
    opener = build_opener(*handlers)
    response = None
    for attempt in range(min(attempts, 3)):
        try:
            time.sleep(max(0, min(float(interval), 10)))
            response = opener.open(Request(url, headers={"User-Agent": "HydroLite-DataHub/1", **(headers or {})}), timeout=15)
            response.hydrolite_redirect_chain = list(redirects)
            break
        except HTTPError as exc:
            if exc.code == 304:
                response = exc
                break
            status = "auth_required" if exc.code in {401, 403} else "rate_limited" if exc.code == 429 else "remote_unavailable"
            delay = exc.headers.get("Retry-After", "")
            if attempt == min(attempts, 3) - 1 or exc.code not in {429, 500, 502, 503, 504}:
                raise ConnectorError(status, f"Provider HTTP {exc.code}") from exc
            # Long Retry-After is reported, never retried earlier than requested.
            if delay and (not delay.isdigit() or int(delay) > 10):
                raise ConnectorError(status, "Provider requests delayed retry; try again later") from exc
            time.sleep(max(float(delay or 0), 2 ** attempt))
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == min(attempts, 3) - 1:
                raise ConnectorError(_network_failure(exc), "Provider network request failed") from exc
            time.sleep(2 ** attempt)
    try:
        yield response
    finally:
        if response:
            response.close()
