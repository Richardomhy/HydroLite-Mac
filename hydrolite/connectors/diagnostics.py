"""Sanitized, read-only diagnostics for configured public connectors."""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from hydrolite.connectors.public import provider_config
from hydrolite.connectors.transport import (
    ConnectorError,
    NetworkSecurityPolicy,
    PublicRedirect,
    _network_failure,
    validate_public_url,
)


def _proxy_summary():
    result = {}
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        value = os.environ.get(name) or os.environ.get(name.lower())
        if not value:
            result[name] = {"status": "absent"}
            continue
        hosts = []
        for part in value.split(",")[:8]:
            parsed = urlsplit(part if "://" in part else "//" + part.strip())
            if parsed.hostname:
                hosts.append(parsed.hostname)
        result[name] = {"status": "present", "hosts": hosts}
    return result


def _resolve(host, port):
    rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = sorted({row[4][0].split("%", 1)[0] for row in rows})
    return [
        {
            "address": address,
            "family": "IPv6" if ipaddress.ip_address(address).version == 6 else "IPv4",
            "classification": _classify_address(ipaddress.ip_address(address)),
        }
        for address in addresses
    ]


def _classify_address(address):
    if address.is_loopback:
        return "loopback"
    if address.is_link_local:
        return "link_local"
    if address.is_private:
        return "private"
    if address.is_reserved or address.is_multicast or not address.is_global:
        return "reserved_or_non_global"
    return "public"


def diagnose_url(url, allowed_hosts, *, probe=True):
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        addresses = _resolve(host, parts.port or 443)
        dns_status = "resolved" if addresses else "dns_failure"
    except (OSError, ValueError):
        addresses, dns_status = [], "dns_failure"
    result = {
        "https_target": f"{parts.scheme}://{host}{parts.path or '/'}",
        "hostname": host,
        "resolved_addresses": addresses,
        "dns_source": "system resolver via socket.getaddrinfo",
        "proxy_environment": _proxy_summary(),
        "redirect_chain": [],
        "final_hostname": host,
        "status": dns_status,
        "block_reason": None,
    }
    try:
        validate_public_url(url, allowed_hosts)
    except ConnectorError as exc:
        result.update(status=exc.status, block_reason=str(exc))
        return result
    if not probe:
        result["status"] = "public_address_validated"
        return result
    redirect_rows = []
    opener = build_opener(PublicRedirect(allowed_hosts, NetworkSecurityPolicy.PRODUCTION_PUBLIC_ONLY, redirect_rows))
    try:
        with opener.open(Request(url, method="HEAD", headers={"User-Agent": "HydroLite-DataHub-Diagnostic/1"}), timeout=5) as response:
            result.update(status="healthy", http_status=response.status, final_hostname=urlsplit(response.geturl()).hostname)
    except ConnectorError as exc:
        result.update(status=exc.status, block_reason=str(exc))
    except HTTPError as exc:
        status = "auth_required" if exc.code in {401, 403} else "rate_limited" if exc.code == 429 else "remote_unavailable"
        result.update(status=status, http_status=exc.code, block_reason=f"Provider returned HTTP {exc.code}")
    except (URLError, TimeoutError, OSError) as exc:
        result.update(status=_network_failure(exc), block_reason="Bounded HTTPS probe failed")
    finally:
        result["redirect_chain"] = redirect_rows
    return result


def diagnose_connector_network(connector_id, *, probe=True):
    providers = provider_config()
    key = "earth_search" if connector_id == "stac" else connector_id
    config = providers.get(key, {})
    endpoint = config.get("endpoint")
    hosts = config.get("allowed_hosts", [])
    if not endpoint or not hosts:
        return {
            "connector_id": connector_id,
            "status": "configuration_error",
            "reason": "No verified public endpoint is configured for this connector",
            "proxy_environment": _proxy_summary(),
            "redirect_chain": [],
        }
    result = diagnose_url(endpoint, hosts, probe=probe)
    return {"connector_id": connector_id, **result}


class ConnectorNetworkDiagnostic:
    """Read-only diagnostics; provider probes are bounded HTTPS HEAD requests."""

    def run(self, connector_id, *, probe=True):
        return diagnose_connector_network(connector_id, probe=probe)
