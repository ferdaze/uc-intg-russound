"""
Constants for the Russound Integration.

Configuration dataclasses and simple command definitions.

Note: this module must not use ``from __future__ import annotations``; the config
manager inspects the field types at runtime to deserialize ``list[ZoneConfig]``.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from dataclasses import dataclass, field
from enum import StrEnum

DEFAULT_PORT = 9621
"""Russound RIO TCP port."""


@dataclass
class ZoneConfig:
    """A zone exposed as a media player entity."""

    controller: int
    """Controller number (1 for a single MCA-88, 2..6 for daisy-chained controllers)."""

    zone: int
    """Zone number on the controller (1..8 on the MCA-88)."""

    name: str
    """Zone name as configured on the controller."""

    @property
    def key(self) -> str:
        """Return a short identifier used in entity ids, e.g. ``c1z3``."""
        return f"c{self.controller}z{self.zone}"


@dataclass
class DeviceConfig:
    """Configuration of one Russound controller (system)."""

    identifier: str
    """Unique identifier, derived from the controller MAC address."""

    name: str
    """Friendly name of the system."""

    address: str
    """IP address or hostname of the controller."""

    port: int = DEFAULT_PORT
    """RIO TCP port."""

    model: str = ""
    """Controller type reported by the device, e.g. ``MCA-88``."""

    zones: list[ZoneConfig] = field(default_factory=list)
    """Zones exposed as media player entities."""


class SimpleCommands(StrEnum):
    """Additional commands shown as buttons for each zone entity."""

    BASS_UP = "BASS_UP"
    BASS_DOWN = "BASS_DOWN"
    TREBLE_UP = "TREBLE_UP"
    TREBLE_DOWN = "TREBLE_DOWN"
    BALANCE_LEFT = "BALANCE_LEFT"
    BALANCE_RIGHT = "BALANCE_RIGHT"
    LOUDNESS_ON = "LOUDNESS_ON"
    LOUDNESS_OFF = "LOUDNESS_OFF"
    LOUDNESS_TOGGLE = "LOUDNESS_TOGGLE"
    TONE_RESET = "TONE_RESET"
    ALL_ZONES_ON = "ALL_ZONES_ON"
    ALL_ZONES_OFF = "ALL_ZONES_OFF"
    SOURCE_1 = "SOURCE_1"
    SOURCE_2 = "SOURCE_2"
    SOURCE_3 = "SOURCE_3"
    SOURCE_4 = "SOURCE_4"
    SOURCE_5 = "SOURCE_5"
    SOURCE_6 = "SOURCE_6"
    SOURCE_7 = "SOURCE_7"
    SOURCE_8 = "SOURCE_8"


SOURCE_COMMAND_PREFIX = "SOURCE_"
