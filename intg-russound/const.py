"""
Constants and configuration types for the Russound RIO integration.

:copyright: (c) 2026 by Jeff Ferdinandsen.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from dataclasses import dataclass, field
from enum import StrEnum

# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------

DEFAULT_PORT = 9621
"""Default RIO TCP port. All MCA/C-Series controllers listen here.

If you reach the controller through an RS-232 <-> IP bridge, use whatever
port the bridge exposes instead.
"""

CONNECT_TIMEOUT = 10.0
"""Seconds to wait for the initial RIO handshake during setup."""

# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------

RUSSOUND_MAX_VOLUME = 50
"""RIO exposes zone volume as an integer 0..50."""

UC_MAX_VOLUME = 100
"""The Remote's media-player entity uses 0..100."""

VOLUME_STEPS = RUSSOUND_MAX_VOLUME
"""Advertised volume steps so one tick on the Remote == one RIO volume step."""


def russound_to_uc_volume(volume: int | None) -> int | None:
    """Convert a RIO volume (0..50) to a Remote volume (0..100)."""
    if volume is None:
        return None
    return max(0, min(UC_MAX_VOLUME, round(volume * UC_MAX_VOLUME / RUSSOUND_MAX_VOLUME)))


def uc_to_russound_volume(volume: int | float | str | None) -> int:
    """Convert a Remote volume (0..100) to a RIO volume (0..50)."""
    if volume is None:
        return 0
    try:
        value = float(volume)
    except (TypeError, ValueError):
        return 0
    scaled = round(value * RUSSOUND_MAX_VOLUME / UC_MAX_VOLUME)
    return max(0, min(RUSSOUND_MAX_VOLUME, scaled))


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass
class DeviceConfig:
    """
    Persisted configuration for one Russound controller stack.

    One config entry == one RIO connection. Daisy-chained RNET controllers
    behind the primary controller are discovered automatically and do not
    need their own entry.
    """

    identifier: str
    """Stable unique id. MAC address of controller 1 when available, else host_port."""

    name: str
    """Friendly name shown on the Remote."""

    address: str
    """IP address or hostname of the controller (or of the RS-232 <-> IP bridge)."""

    port: int = DEFAULT_PORT
    """RIO TCP port."""

    model: str = ""
    """Controller model reported by RIO, e.g. ``MCA-88``. Informational only."""

    zone_names: dict[str, str] = field(default_factory=dict)
    """Cached ``sub_device_id -> zone name`` map, used to name entities before
    the first connection completes after a Remote reboot."""


# --------------------------------------------------------------------------
# Entity helpers
# --------------------------------------------------------------------------


def zone_sub_id(controller_id: int, zone_id: int) -> str:
    """
    Build the sub-device id used in entity ids.

    Produces e.g. ``c1z3``, giving a final entity id of
    ``media_player.<device_id>.c1z3``.
    """
    return f"c{controller_id}z{zone_id}"


# --------------------------------------------------------------------------
# Simple commands
# --------------------------------------------------------------------------


class SimpleCommands(StrEnum):
    """
    Extra per-zone commands surfaced as buttons in the Remote UI.

    These cover RIO features that have no equivalent media-player feature.
    """

    PARTY_MODE_ON = "PARTY_MODE_ON"
    PARTY_MODE_MASTER = "PARTY_MODE_MASTER"
    PARTY_MODE_OFF = "PARTY_MODE_OFF"
    DO_NOT_DISTURB_ON = "DO_NOT_DISTURB_ON"
    DO_NOT_DISTURB_OFF = "DO_NOT_DISTURB_OFF"
    LOUDNESS_ON = "LOUDNESS_ON"
    LOUDNESS_OFF = "LOUDNESS_OFF"
    BASS_UP = "BASS_UP"
    BASS_DOWN = "BASS_DOWN"
    BASS_FLAT = "BASS_FLAT"
    TREBLE_UP = "TREBLE_UP"
    TREBLE_DOWN = "TREBLE_DOWN"
    TREBLE_FLAT = "TREBLE_FLAT"
    BALANCE_LEFT = "BALANCE_LEFT"
    BALANCE_RIGHT = "BALANCE_RIGHT"
    BALANCE_CENTER = "BALANCE_CENTER"
    ALL_ZONES_OFF = "ALL_ZONES_OFF"
    PRESET_1 = "PRESET_1"
    PRESET_2 = "PRESET_2"
    PRESET_3 = "PRESET_3"
    PRESET_4 = "PRESET_4"
    PRESET_5 = "PRESET_5"
    PRESET_6 = "PRESET_6"


TONE_MIN = -10
TONE_MAX = 10
"""RIO bass/treble/balance range."""

TONE_STEP = 2
"""Step size used by the BASS_UP / TREBLE_DOWN / ... simple commands."""
