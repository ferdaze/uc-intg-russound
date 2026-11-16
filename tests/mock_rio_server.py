"""
A minimal in-process Russound RIO server.

Speaks enough of the protocol for :mod:`aiorussound` to complete a full
connect, metadata load and WATCH subscription cycle, so the integration can
be exercised without a physical controller.

Not a protocol reference - it mirrors what the client actually asks for.
"""

import asyncio
import re
from typing import Any

CONTROLLER_TYPE = "MCA-88"
MAC_ADDRESS = "00:11:22:33:44:55"
FIRMWARE = "07.03.00"
RIO_VERSION = "1.14.00"

ZONE_COUNT = 8
SOURCE_COUNT = 4

GET_RE = re.compile(r"^GET (?P<branch>.+)\.(?P<leaf>\w+)$")
SET_RE = re.compile(r'^SET (?P<branch>.+)\.(?P<leaf>\w+)="(?P<value>[^"]*)"$')
EVENT_RE = re.compile(r"^EVENT (?P<branch>[^!]+)!(?P<event>\w+)\s*(?P<args>.*)$")
WATCH_RE = re.compile(r"^WATCH (?P<branch>.+) (?P<state>ON|OFF)$")


def _is_watched(notification: str, watched: set[str]) -> bool:
    """Return True if a ``N <branch>.<leaf>="value"`` line belongs to a watched branch."""
    key = notification[2:].split("=", 1)[0]
    return key.rsplit(".", 1)[0] in watched


class MockRioServer:
    """Serves the RIO protocol over TCP on localhost."""

    def __init__(self) -> None:
        """Build the initial zone and source state."""
        self.server: asyncio.AbstractServer | None = None
        self.port = 0
        self.received: list[str] = []
        self.connections = 0
        self.silent = False
        """When True the server reads commands but never answers them."""
        self._writers: list[asyncio.StreamWriter] = []

        self.zones: dict[int, dict[str, Any]] = {
            zone_id: {
                "name": f"Zone {zone_id}",
                "status": "OFF",
                "volume": "20",
                "mute": "OFF",
                "currentSource": "1",
                "bass": "0",
                "treble": "0",
                "balance": "0",
                "loudness": "OFF",
            }
            for zone_id in range(1, ZONE_COUNT + 1)
        }
        self.sources: dict[int, dict[str, Any]] = {
            1: {"name": "Sonos", "type": "Cable", "songName": "Test Track",
                "artistName": "Test Artist", "albumName": "Test Album",
                "playStatus": "playing"},
            2: {"name": "Turntable", "type": "Misc Audio"},
            3: {"name": "TV Audio", "type": "Television"},
            4: {"name": "Bluetooth", "type": "Russound Bluetooth Module"},
        }

    async def start(self, port: int = 0) -> int:
        """
        Start listening and return the port.

        :param port: port to bind, or 0 for an ephemeral one. Pass the previous
                     port to bring a stopped server back at the same address.
        """
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        self.port = self.server.sockets[0].getsockname()[1]
        return self.port

    @property
    def open_connections(self) -> int:
        """Number of client connections currently open."""
        return len(self._writers)

    async def drop_connections(self) -> None:
        """Close every client connection but keep listening."""
        for writer in list(self._writers):
            writer.close()
        self._writers.clear()

    async def stop(self) -> None:
        """Close the listener and all client connections."""
        await self.drop_connections()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writers.append(writer)
        self.connections += 1
        # Like the real controller, only notify about branches this particular
        # connection has asked to WATCH. A new connection starts with none.
        watched: set[str] = set()
        try:
            while True:
                raw = await reader.readuntil(b"\r")
                command = raw.decode("iso-8859-1").strip()
                if not command:
                    continue
                self.received.append(command)
                if self.silent:
                    continue
                if match := WATCH_RE.match(command):
                    watched.add(match.group("branch"))
                for response in self._respond(command):
                    if response.startswith("N ") and not _is_watched(response, watched):
                        continue
                    writer.write(f"{response}\r\n".encode("iso-8859-1"))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            if writer in self._writers:
                self._writers.remove(writer)
            writer.close()

    def _respond(self, command: str) -> list[str]:
        if command == "VERSION":
            return [f'S version="{RIO_VERSION}"']

        if match := WATCH_RE.match(command):
            return ["S", *self._snapshot(match.group("branch"))]

        if match := GET_RE.match(command):
            return [self._get(match.group("branch"), match.group("leaf"))]

        if match := SET_RE.match(command):
            return self._set(
                match.group("branch"), match.group("leaf"), match.group("value")
            )

        if match := EVENT_RE.match(command):
            return self._event(
                match.group("branch"),
                match.group("event"),
                match.group("args").strip(),
            )

        return ["E Unsupported command"]

    # -- reads ------------------------------------------------------------

    def _get(self, branch: str, leaf: str) -> str:
        if branch == "C[1]":
            values = {
                "type": CONTROLLER_TYPE,
                "macAddress": MAC_ADDRESS,
                "firmwareVersion": FIRMWARE,
            }
            if leaf in values:
                return f'S {branch}.{leaf}="{values[leaf]}"'
            return "E Unknown key"

        if re.match(r"^C\[\d+]$", branch):
            # Only controller 1 exists in this mock.
            return "E No such controller"

        if zone := self._zone_for(branch):
            if leaf in zone:
                return f'S {branch}.{leaf}="{zone[leaf]}"'
            return "E Unknown key"

        # Zone/source exclusion: every source is enabled in every zone.
        if re.match(r"^C\[\d+]\.Z\[\d+]\.S\[\d+]$", branch) and leaf == "enabled":
            return f'S {branch}.enabled="TRUE"'

        if match := re.match(r"^S\[(\d+)]$", branch):
            source = self.sources.get(int(match.group(1)))
            if source and leaf in source:
                return f'S {branch}.{leaf}="{source[leaf]}"'
            return "E Unknown source"

        return "E Unknown branch"

    def _zone_for(self, branch: str) -> dict[str, Any] | None:
        match = re.match(r"^C\[(\d+)]\.Z\[(\d+)]$", branch)
        if not match or int(match.group(1)) != 1:
            return None
        return self.zones.get(int(match.group(2)))

    def _snapshot(self, branch: str) -> list[str]:
        """Emit the current value of every key under a freshly watched branch."""
        if zone := self._zone_for(branch):
            return [f'N {branch}.{key}="{value}"' for key, value in zone.items()]
        if match := re.match(r"^S\[(\d+)]$", branch):
            source = self.sources.get(int(match.group(1)), {})
            return [f'N {branch}.{key}="{value}"' for key, value in source.items()]
        return []

    # -- writes -----------------------------------------------------------

    def _set(self, branch: str, leaf: str, value: str) -> list[str]:
        zone = self._zone_for(branch)
        if zone is None:
            return ["E Unknown branch"]
        zone[leaf] = value
        return ["S", f'N {branch}.{leaf}="{value}"']

    def _event(self, branch: str, event: str, args: str) -> list[str]:
        zone = self._zone_for(branch)
        if zone is None:
            return ["E Unknown branch"]

        notifications: list[str] = []

        def change(key: str, value: str) -> None:
            zone[key] = value
            notifications.append(f'N {branch}.{key}="{value}"')

        match event:
            case "ZoneOn":
                change("status", "ON")
            case "ZoneOff":
                change("status", "OFF")
            case "ZoneMuteOn":
                change("mute", "ON")
            case "ZoneMuteOff":
                change("mute", "OFF")
            case "KeyRelease" if args == "Mute":
                change("mute", "OFF" if zone["mute"] == "ON" else "ON")
            case "KeyPress" if args == "VolumeUp":
                change("volume", str(min(50, int(zone["volume"]) + 1)))
            case "KeyPress" if args == "VolumeDown":
                change("volume", str(max(0, int(zone["volume"]) - 1)))
            case "KeyPress" if args.startswith("Volume "):
                change("volume", args.split(" ", 1)[1])
            case "SelectSource":
                change("currentSource", args)
            case "AllOff":
                for other in self.zones.values():
                    other["status"] = "OFF"
                notifications.extend(
                    f'N C[1].Z[{zone_id}].status="OFF"' for zone_id in self.zones
                )

        return ["S", *notifications]
