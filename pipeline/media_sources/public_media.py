"""Bounded HTTPS reads for public media APIs and federated download hosts.

DNS is resolved once per hop, checked, and pinned to the TLS connection. No
credentials, private addresses, arbitrary ports, or automatic auth are used.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
import time
from urllib.parse import urlsplit, urljoin


class AccessDenied(RuntimeError):
    pass


def public_addresses(host):
    addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("Public media host resolved to a non-public address")
    return addresses


def validate_url(url, hosts=None):
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Only public HTTPS URLs without credentials are supported")
    if hosts and not any(p.hostname == h or p.hostname.endswith("." + h) for h in hosts):
        raise ValueError("Unexpected provider host")
    return p


def fetch(url, *, max_bytes=8 * 1024 * 1024, hosts=None, timeout=30, wall_seconds=180):
    started = time.monotonic()
    for _ in range(4):
        p = validate_url(url, hosts)
        addresses = public_addresses(p.hostname)
        connection = http.client.HTTPSConnection(p.hostname, timeout=timeout)
        try:
            # Connect to the checked IP, preserving certificate/SNI validation.
            sock = socket.create_connection((addresses[0], 443), timeout=timeout)
            try:
                connection.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=p.hostname)
            except Exception:
                sock.close()
                raise
            connection.request("GET", (p.path or "/") + ("?" + p.query if p.query else ""), headers={
                "User-Agent": "AI-News-Daily-media-research/1.0 (https://github.com/jcval94/AI-News-Daily)",
                "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = urljoin(url, response.getheader("Location", ""))
                continue
            if response.status in (401, 403, 429):
                raise AccessDenied(f"Public provider denied access (HTTP {response.status})")
            if response.status != 200:
                raise RuntimeError(f"Public provider HTTP {response.status}")
            if int(response.getheader("Content-Length", "0")) > max_bytes:
                raise ValueError("Public media exceeds byte budget")
            chunks, size = [], 0
            while True:
                if time.monotonic() - started > wall_seconds:
                    raise TimeoutError("Public media read exceeded wall-time budget")
                chunk = response.read(min(256 * 1024, max_bytes - size + 1))
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Public media exceeds byte budget")
        finally:
            connection.close()
    raise ValueError("Too many public media redirects")


def json_get(url, *, hosts=None):
    return json.loads(fetch(url, hosts=hosts))
