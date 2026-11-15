"""
Russound controller discovery.

Russound MCA/C-Series controllers do not advertise themselves over mDNS or
SSDP, so this scans the Remote's own IPv4 /24 for anything listening on the
RIO port and confirms each hit by asking it for its RIO version and
controller type.

:copyright: (c) 2026 by Jeff Ferdinandsen.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import ipaddress
import logging
import socket

from const import DEFAULT_PORT
from ucapi_framework import BaseDiscovery, DiscoveredDevice

_LOG = logging.getLogger(__name__)

PROBE_TIMEOUT = 1.0
"""Seconds to wait for a RIO reply from a candidate host."""

MAX_CONCURRENT_PROBES = 48
"""Keep the scan gentle enough for the Remote's limited resources."""


def local_ipv4() -> str | None:
    """
    Determine the Remote's primary IPv4 address.

    Uses a connectionless UDP socket, so no traffic is actually sent.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


class RussoundDiscovery(BaseDiscovery):
    """Scan the local subnet for controllers speaking RIO."""

    def __init__(self, port: int = DEFAULT_PORT, timeout: int = 30) -> None:
        """
        Initialize discovery.

        :param port: RIO port to probe
        :param timeout: overall budget for the scan, in seconds
        """
        super().__init__(timeout)
        self.port = port

    async def discover(self) -> list[DiscoveredDevice]:
        """
        Scan the local /24 and return every controller that answers RIO.

        :return: discovered controllers, empty if none respond
        """
        self._discovered_devices.clear()

        host_ip = local_ipv4()
        if host_ip is None:
            _LOG.warning("Could not determine local IP address, skipping scan")
            return self._discovered_devices

        network = ipaddress.ip_network(f"{host_ip}/24", strict=False)
        _LOG.info("Scanning %s for Russound controllers on port %d", network, self.port)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROBES)

        async def guarded(ip: str) -> DiscoveredDevice | None:
            async with semaphore:
                return await self.probe_device(ip, self.port)

        tasks = [
            asyncio.create_task(guarded(str(ip)))
            for ip in network.hosts()
            if str(ip) != host_ip
        ]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=self.timeout
            )
        except (TimeoutError, asyncio.TimeoutError):
            _LOG.warning("Discovery scan timed out after %ds", self.timeout)
            for task in tasks:
                task.cancel()
            results = [task.result() if task.done() and not task.cancelled() else None for task in tasks]

        for result in results:
            if isinstance(result, DiscoveredDevice):
                self._discovered_devices.append(result)

        _LOG.info("Discovery finished: %d controller(s)", len(self._discovered_devices))
        return self._discovered_devices

    async def probe_device(self, ip: str, port: int) -> DiscoveredDevice | None:
        """
        Ask one host whether it speaks RIO.

        :param ip: candidate IP address
        :param port: RIO port
        :return: a DiscoveredDevice on success, otherwise None
        """
        writer = None
        try:
            async with asyncio.timeout(PROBE_TIMEOUT):
                reader, writer = await asyncio.open_connection(ip, port)

                writer.write(b"VERSION\r")
                await writer.drain()
                version = _value(await reader.readline())
                if not version:
                    return None

                writer.write(b"GET C[1].type\r")
                await writer.drain()
                model = _value(await reader.readline()) or "Russound"

            _LOG.debug("Found %s at %s (RIO v%s)", model, ip, version)
            return DiscoveredDevice(
                identifier=f"{ip}_{port}".replace(".", "_"),
                name=model,
                address=ip,
                extra_data={"model": model, "port": port, "rio_version": version},
            )
        except (OSError, TimeoutError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            return None
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass


def _value(raw: bytes) -> str | None:
    """
    Extract the payload from a RIO response line.

    RIO replies look like ``S C[1].type="MCA-88"`` or ``S 1.14.00``; error
    replies start with ``E``.
    """
    try:
        text = raw.decode("iso-8859-1").strip()
    except UnicodeDecodeError:
        return None
    if not text or text.startswith("E"):
        return None
    if text.startswith("S "):
        text = text[2:].strip()
    if "=" in text:
        text = text.split("=", 1)[1]
    return text.strip().strip('"') or None
