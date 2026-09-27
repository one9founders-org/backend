"""Reject URL fetches that target local or non-routable hosts."""

from __future__ import annotations

import ipaddress
import socket

_BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata.google",
}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal")


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not ip.is_global


def host_is_blocked(host: str) -> bool:
    """True when a hostname is local, metadata, or resolves to a non-public IP."""
    name = (host or "").strip().lower().rstrip(".")
    if not name:
        return True
    if name in _BLOCKED_HOSTS or name.endswith(_BLOCKED_SUFFIXES):
        return True
    try:
        literal = ipaddress.ip_address(name)
    except ValueError:
        literal = None
    if literal is not None:
        return _blocked_ip(literal)
    try:
        infos = socket.getaddrinfo(name, None)
    except socket.gaierror:
        return False
    for info in infos:
        addr = str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _blocked_ip(ip):
            return True
    return False
