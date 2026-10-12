"""Wait for the configured local bind address, including DHCP and IPv6."""
from __future__ import annotations

import socket
import time


def address_available(host: str) -> bool:
    try:
        addresses = socket.getaddrinfo(host, 0, type=socket.SOCK_STREAM)
        for family, kind, protocol, _, address in addresses:
            try:
                with socket.socket(family, kind, protocol) as connection:
                    connection.bind(address)
                return True
            except OSError:
                continue
    except OSError:
        pass
    return False


def wait_for_address(host: str, timeout: float = 60, interval: float = 0.5) -> bool:
    if timeout < 0 or interval <= 0:
        raise ValueError("Invalid network wait timing")
    deadline = time.monotonic() + timeout
    while not address_available(host):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(interval, remaining))
    return True
