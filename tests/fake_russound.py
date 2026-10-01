"""
Fake Russound controller speaking the RIO protocol, for tests.

Emulates a single MCA-88: 8 zones, 8 sources, WATCH notifications and the zone
events and variables the integration uses.
"""

import asyncio
import re

_GET_RE = re.compile(r"^GET (?P<key>\S+)$")
_SET_RE = re.compile(r'^SET (?P<key>\S+)="(?P<value>.*)"$')
_WATCH_RE = re.compile(r"^WATCH (?P<branch>\S+) (?P<mode>ON|OFF)$")
_EVENT_RE = re.compile(r"^EVENT C\[(?P<c>\d+)\]\.Z\[(?P<z>\d+)\]!(?P<event>\w+)(?: (?P<args>.*))?$")


class FakeRussound:
    """Minimal RIO server emulating an MCA-88."""

    def __init__(self, zones: int = 8, sources: int = 8, version: str = "1.10.00", model: str = "MCA-88"):
        self.version = version
        self.model = model
        self.mac = "00:21:C7:0A:0B:0C"
        self.values: dict[str, dict[str, str]] = {}
        for zone in range(1, zones + 1):
            self.values[f"C[1].Z[{zone}]"] = {
                "name": f"Zone {zone}",
                "status": "OFF",
                "volume": "20",
                "mute": "OFF",
                "currentSource": "1",
                "bass": "0",
                "treble": "0",
                "balance": "0",
                "loudness": "OFF",
                "turnOnVolume": "20",
            }
        for source in range(1, sources + 1):
            self.values[f"S[{source}]"] = {"name": f"Source {source}", "type": "Misc Audio"}
        self.commands: list[str] = []
        self._watches: dict[asyncio.StreamWriter, set[str]] = {}
        self._server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.drop_clients()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    def drop_clients(self) -> None:
        """Close all client connections (simulates a network drop)."""
        for writer in list(self._watches):
            writer.close()
        self._watches.clear()

    @property
    def client_count(self) -> int:
        return len(self._watches)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._watches[writer] = set()
        try:
            while True:
                try:
                    raw = await reader.readuntil(b"\r")
                except (asyncio.IncompleteReadError, ConnectionError):
                    break
                command = raw.decode().strip()
                self.commands.append(command)
                for line in self._process(writer, command):
                    writer.write(f"{line}\r\n".encode())
                await writer.drain()
        finally:
            self._watches.pop(writer, None)
            writer.close()

    def _notify(self, branch: str, leaf: str) -> list[tuple[asyncio.StreamWriter, str]]:
        value = self.values[branch][leaf]
        return [(w, f'N {branch}.{leaf}="{value}"') for w, branches in self._watches.items() if branch in branches]

    def _set(self, branch: str, leaf: str, value: str) -> None:
        self.values[branch][leaf] = value
        for writer, line in self._notify(branch, leaf):
            writer.write(f"{line}\r\n".encode())

    def _process(self, writer: asyncio.StreamWriter, command: str) -> list[str]:
        if command == "VERSION":
            return [f'S VERSION="{self.version}"']

        if match := _GET_RE.match(command):
            key = match["key"]
            if key == "C[1].type":
                return [f'S C[1].type="{self.model}"']
            if key == "C[1].macAddress":
                return [f'S C[1].macAddress="{self.mac}"']
            branch, leaf = key.rsplit(".", 1)
            if branch in self.values and leaf in self.values[branch]:
                return [f'S {key}="{self.values[branch][leaf]}"']
            return ["E Invalid Command"]

        if match := _WATCH_RE.match(command):
            branch = match["branch"]
            if branch not in self.values:
                return ["E Invalid Command"]
            if match["mode"] == "ON":
                self._watches[writer].add(branch)
                return ["S"] + [f'N {branch}.{leaf}="{value}"' for leaf, value in self.values[branch].items()]
            self._watches[writer].discard(branch)
            return ["S"]

        if match := _SET_RE.match(command):
            branch, leaf = match["key"].rsplit(".", 1)
            if branch not in self.values:
                return ["E Invalid Command"]
            response = ["S"]
            self._set(branch, leaf, match["value"])
            return response

        if match := _EVENT_RE.match(command):
            return self._event(f"C[{match['c']}].Z[{match['z']}]", match["event"], (match["args"] or "").split())

        return ["E Invalid Command"]

    def _event(self, branch: str, event: str, args: list[str]) -> list[str]:
        if branch not in self.values:
            return ["E Invalid Command"]
        zone = self.values[branch]
        match event, args:
            case "ZoneOn", []:
                self._set(branch, "status", "ON")
            case "ZoneOff", []:
                self._set(branch, "status", "OFF")
            case "AllOn" | "AllOff", []:
                for other in [b for b in self.values if b.startswith("C[")]:
                    self._set(other, "status", "ON" if event == "AllOn" else "OFF")
            case "KeyPress", ["Volume", level]:
                self._set(branch, "volume", level)
            case "KeyPress", ["VolumeUp"]:
                self._set(branch, "volume", str(min(50, int(zone["volume"]) + 1)))
            case "KeyPress", ["VolumeDown"]:
                self._set(branch, "volume", str(max(0, int(zone["volume"]) - 1)))
            case "KeyRelease", ["Mute"]:
                self._set(branch, "mute", "OFF" if zone["mute"] == "ON" else "ON")
            case "ZoneMuteOn", []:
                self._set(branch, "mute", "ON")
            case "ZoneMuteOff", []:
                self._set(branch, "mute", "OFF")
            case "SelectSource", [source]:
                if f"S[{source}]" not in self.values:
                    return ["E Invalid Command"]
                self._set(branch, "currentSource", source)
            case "KeyPress", [_key]:
                pass
            case _:
                return ["E Invalid Command"]
        return ["S"]
