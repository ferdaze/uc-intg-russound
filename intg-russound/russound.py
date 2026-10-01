"""
Russound System Model.

State containers for zones and sources, and helpers to discover the controllers, zones
and sources of a Russound system over RIO.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
import re
from dataclasses import dataclass, field

from rio import RioClient, RioCommandError

_LOG = logging.getLogger(__name__)

MAX_CONTROLLERS = 6
"""Controllers that can be daisy-chained over RNET (C[1] is the one we talk to)."""

MAX_SOURCES = 16
"""Highest source number probed during discovery."""

MAX_VOLUME = 50
"""Russound zone volume range is 0..50."""

ZONES_PER_CONTROLLER = {
    "MCA-88": 8,
    "MCA-88X": 8,
    "MCA-C5": 8,
    "MCA-C6": 8,
    "SMZ8": 8,
    "SMZ16": 16,
    "SMZ16-PRE": 16,
    "MCA-66": 6,
    "MCA-C3": 6,
}
DEFAULT_ZONES_PER_CONTROLLER = 8

RNET_CAPABLE = {"MCA-88", "MCA-88X", "MCA-66", "MCA-C3", "MCA-C5", "MCA-C6", "SMZ8"}
"""Controller types that support daisy-chained controllers."""

_ZONE_BRANCH_RE = re.compile(r"^C\[(\d+)\]\.Z\[(\d+)\]$")
_SOURCE_BRANCH_RE = re.compile(r"^S\[(\d+)\]$")


def zone_branch(controller: int, zone: int) -> str:
    """Return the RIO branch for a zone, e.g. ``C[1].Z[3]``."""
    return f"C[{controller}].Z[{zone}]"


def source_branch(source: int) -> str:
    """Return the RIO branch for a source, e.g. ``S[2]``."""
    return f"S[{source}]"


def parse_zone_branch(branch: str) -> tuple[int, int] | None:
    """Return (controller, zone) for a zone branch, or None."""
    match = _ZONE_BRANCH_RE.match(branch)
    return (int(match[1]), int(match[2])) if match else None


def parse_source_branch(branch: str) -> int | None:
    """Return the source number for a source branch, or None."""
    match = _SOURCE_BRANCH_RE.match(branch)
    return int(match[1]) if match else None


def version_tuple(version: str | None) -> tuple[int, ...]:
    """Convert a RIO version like ``1.10.00`` to a comparable tuple; unknown -> (0,)."""
    if not version:
        return (0,)
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


def _as_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.upper() in ("ON", "TRUE", "1")


def _as_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


@dataclass
class ZoneState:
    """Current state of one zone, fed by RIO notifications."""

    controller: int
    zone: int
    name: str
    values: dict[str, str | None] = field(default_factory=dict)

    def apply(self, leaf: str, value: str | None) -> bool:
        """Store a notified value; return True if it changed."""
        if leaf == "name" and value:
            changed = self.name != value
            self.name = value
            self.values[leaf] = value
            return changed
        if self.values.get(leaf) == value and leaf in self.values:
            return False
        self.values[leaf] = value
        return True

    def clear(self) -> None:
        """Forget all values (used when the connection is lost)."""
        self.values.clear()

    @property
    def known(self) -> bool:
        """Return True once the zone's power state has been reported."""
        return "status" in self.values

    @property
    def power(self) -> bool | None:
        """Return True if the zone is on."""
        return _as_bool(self.values.get("status"))

    @property
    def volume(self) -> int | None:
        """Return the volume, 0..50."""
        return _as_int(self.values.get("volume"))

    @property
    def muted(self) -> bool | None:
        """Return True if the zone is muted."""
        return _as_bool(self.values.get("mute"))

    @property
    def source(self) -> int | None:
        """Return the selected source number."""
        return _as_int(self.values.get("currentSource"))

    @property
    def bass(self) -> int | None:
        """Return bass, -10..10."""
        return _as_int(self.values.get("bass"))

    @property
    def treble(self) -> int | None:
        """Return treble, -10..10."""
        return _as_int(self.values.get("treble"))

    @property
    def balance(self) -> int | None:
        """Return balance, -10 (left)..10 (right)."""
        return _as_int(self.values.get("balance"))

    @property
    def loudness(self) -> bool | None:
        """Return True if loudness is on."""
        return _as_bool(self.values.get("loudness"))

    @property
    def turn_on_volume(self) -> int | None:
        """Return the volume the zone turns on with, 0..50."""
        return _as_int(self.values.get("turnOnVolume"))


@dataclass
class SourceState:
    """Current state of one source, fed by RIO notifications."""

    source: int
    name: str
    values: dict[str, str | None] = field(default_factory=dict)

    def apply(self, leaf: str, value: str | None) -> bool:
        """Store a notified value; return True if it changed."""
        if leaf == "name" and value:
            changed = self.name != value
            self.name = value
            self.values[leaf] = value
            return changed
        if self.values.get(leaf) == value and leaf in self.values:
            return False
        self.values[leaf] = value
        return True

    def _first(self, *keys: str) -> str | None:
        for key in keys:
            value = self.values.get(key)
            if value:
                return value
        return None

    @property
    def title(self) -> str | None:
        """Return the song title, or the station for tuner sources."""
        return self._first("songName", "channelName", "programServiceName", "channel")

    @property
    def artist(self) -> str | None:
        """Return the artist, or radio text for tuner sources."""
        return self._first("artistName", "radioText")

    @property
    def album(self) -> str | None:
        """Return the album or playlist name."""
        return self._first("albumName", "playlistName")

    @property
    def cover_art_url(self) -> str | None:
        """Return the cover art URL, if the source provides one."""
        return self._first("coverArtURL")

    @property
    def play_status(self) -> str | None:
        """Return the play status (``playing``, ``paused``, ``stopped``...), if reported."""
        value = self.values.get("playStatus")
        return value.lower() if value else None


@dataclass
class ControllerInfo:
    """A controller found during discovery."""

    controller: int
    type: str
    mac_address: str | None = None
    firmware_version: str | None = None


@dataclass
class ZoneInfo:
    """A zone found during discovery."""

    controller: int
    zone: int
    name: str


@dataclass
class SystemInfo:
    """Result of discovering a Russound system."""

    rio_version: str | None
    controllers: list[ControllerInfo]
    zones: list[ZoneInfo]
    sources: dict[int, str]

    @property
    def primary(self) -> ControllerInfo:
        """Return the controller the connection terminates at (C[1])."""
        return self.controllers[0]


async def _get_optional(client: RioClient, key: str) -> str | None:
    """GET a variable, returning None if the controller does not know it."""
    try:
        return await client.get(key)
    except RioCommandError:
        return None


async def discover_sources(client: RioClient) -> dict[int, str]:
    """Return {source number: name} for all configured sources."""
    sources: dict[int, str] = {}
    for source in range(1, MAX_SOURCES + 1):
        try:
            name = await client.get(f"{source_branch(source)}.name")
        except RioCommandError:
            break
        if name:
            sources[source] = name
    return sources


async def discover_system(client: RioClient) -> SystemInfo:
    """
    Discover controllers, zones and sources.

    :param client: A connected RIO client
    :raises RioConnectionError: If the connection fails during discovery
    :raises RioCommandError: If the primary controller cannot be identified
    """
    rio_version = await client.version()
    _LOG.info("RIO protocol version %s", rio_version)

    primary_type = await client.get("C[1].type")
    if not primary_type:
        raise RioCommandError("No primary controller found")

    controllers = [
        ControllerInfo(
            1,
            primary_type,
            await _get_optional(client, "C[1].macAddress"),
            await _get_optional(client, "C[1].firmwareVersion"),
        )
    ]
    if primary_type in RNET_CAPABLE:
        for controller in range(2, MAX_CONTROLLERS + 1):
            controller_type = await _get_optional(client, f"C[{controller}].type")
            if controller_type:
                controllers.append(ControllerInfo(controller, controller_type))

    zones: list[ZoneInfo] = []
    for info in controllers:
        max_zones = ZONES_PER_CONTROLLER.get(info.type, DEFAULT_ZONES_PER_CONTROLLER)
        for zone in range(1, max_zones + 1):
            try:
                name = await client.get(f"{zone_branch(info.controller, zone)}.name")
            except RioCommandError:
                break
            if name:
                zones.append(ZoneInfo(info.controller, zone, name))

    sources = await discover_sources(client)
    _LOG.info(
        "Discovered %s: %d controller(s), %d zone(s), %d source(s)",
        primary_type,
        len(controllers),
        len(zones),
        len(sources),
    )
    return SystemInfo(rio_version, controllers, zones, sources)
