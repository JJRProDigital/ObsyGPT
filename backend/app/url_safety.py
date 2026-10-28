"""Shared URL safety validation for tools that fetch or navigate to URLs.

Blocks SSRF vectors: loopback/private/link-local/reserved IPs, localhost
hostnames, and hostnames that resolve to private addresses. Used by
web_fetch, browser navigation, URL skills, and the MCP gateway.
"""

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    """Raised when a URL points at a forbidden (private/local) target."""


def _is_forbidden_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified


def validate_public_url(url: str, *, resolve_dns: bool = True, label: str = "URLs") -> str:
    """Validates that a URL targets a public http(s) origin; returns the cleaned URL.

    Raises UnsafeUrlError otherwise. Set resolve_dns=False to skip the DNS
    resolution check. A DNS resolution failure is not treated as unsafe —
    the actual fetch will surface it.

    DNS rebinding (TOCTOU between validation and fetch) is out of scope here.
    """
    cleaned = (url or "").strip().rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError(f"Only HTTP and HTTPS {label} are allowed.")
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise UnsafeUrlError(f"URL host is required.")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeUrlError(f"Private or local {label} are not allowed.")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        if _is_forbidden_ip(address):
            raise UnsafeUrlError(f"Private or local {label} are not allowed.")
        return cleaned

    if resolve_dns:
        try:
            resolved = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return cleaned
        for _, _, _, _, sockaddr in resolved:
            candidate = sockaddr[0]
            try:
                ip = ipaddress.ip_address(candidate.split("%")[0])
            except ValueError:
                continue
            if _is_forbidden_ip(ip):
                raise UnsafeUrlError(f"Private or local {label} are not allowed.")
    return cleaned
