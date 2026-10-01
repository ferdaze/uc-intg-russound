"""
Russound Device Module.

Maintains the persistent RIO connection to a Russound controller, tracks zone and
source state from RIO notifications and offers zone control commands.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
from asyncio import AbstractEventLoop

from const import DeviceConfig
from rio import RioClient, RioConnectionError, split_key
from russound import (
    MAX_VOLUME,
    SourceState,
    ZoneState,
    discover_sources,
    parse_source_branch,
    parse_zone_branch,
    source_branch,
    version_tuple,
    zone_branch,
)
from ucapi_framework import BaseConfigManager, PersistentConnectionDevice

_LOG = logging.getLogger(__name__)

UPDATE_DEBOUNCE = 0.05
"""Seconds to collect notifications before pushing state to the entities."""

TONE_MIN = -10
TONE_MAX = 10

MUTE_ON_OFF_MIN_VERSION = (1, 9, 0)
"""RIO version that added the ZoneMuteOn / ZoneMuteOff events."""


class RussoundDevice(PersistentConnectionDevice):
    """
    A Russound controller (system) with one or more zones.

    The connection loop of :class:`PersistentConnectionDevice` handles reconnects with
    exponential backoff. Each connection subscribes (WATCH) to every configured zone and
    every source; the controller pushes changes, which are forwarded to the entities via
    ``push_update()``.
    """

    def __init__(
        self,
        device_config: DeviceConfig,
        loop: AbstractEventLoop | None = None,
        config_manager: BaseConfigManager | None = None,
        driver=None,
    ) -> None:
        """
        Initialize the device.

        :param device_config: Configuration for this controller
        :param loop: Event loop
        :param config_manager: Configuration manager instance
        :param driver: Integration driver instance
        """
        super().__init__(
            device_config=device_config,
            loop=loop,
            backoff_max=30,
            config_manager=config_manager,
            driver=driver,
        )
        self._client: RioClient | None = None
        self._rio_version: str | None = None
        self._zones: dict[tuple[int, int], ZoneState] = {
            (zone.controller, zone.zone): ZoneState(zone.controller, zone.zone, zone.name)
            for zone in device_config.zones
        }
        self._sources: dict[int, SourceState] = {}
        self._update_handle: asyncio.TimerHandle | None = None

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def identifier(self) -> str:
        """Return the device identifier."""
        return self._device_config.identifier

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._device_config.name

    @property
    def address(self) -> str | None:
        """Return the controller address."""
        return self._device_config.address

    @property
    def log_id(self) -> str:
        """Return a log identifier for debugging."""
        return self.name if self.name else self.identifier

    @property
    def is_connected(self) -> bool:
        """Return True while the RIO connection is established and subscribed."""
        return self._connection is not None and self._client is not None and self._client.connected

    @property
    def rio_version(self) -> str | None:
        """Return the RIO protocol version reported by the controller."""
        return self._rio_version

    @property
    def source_names(self) -> list[str]:
        """Return the names of all sources, ordered by source number."""
        return [self._sources[number].name for number in sorted(self._sources)]

    def zone(self, controller: int, zone: int) -> ZoneState | None:
        """Return the state of a zone."""
        return self._zones.get((controller, zone))

    def source(self, number: int | None) -> SourceState | None:
        """Return the state of a source."""
        if number is None:
            return None
        return self._sources.get(number)

    def source_number(self, name: str) -> int | None:
        """Return the source number for a source name (case-insensitive)."""
        wanted = name.strip().casefold()
        for number, source in self._sources.items():
            if source.name.casefold() == wanted:
                return number
        return None

    # =========================================================================
    # Connection Management (PersistentConnectionDevice)
    # =========================================================================

    async def establish_connection(self) -> RioClient:
        """Connect, load the source list and subscribe to zone and source changes."""
        config: DeviceConfig = self._device_config
        client = RioClient(config.address, config.port, on_notification=self._on_notification)
        await client.connect()
        try:
            self._rio_version = await client.version()
            names = await discover_sources(client)
            self._sources = {number: SourceState(number, name) for number, name in names.items()}
            for number in self._sources:
                await client.watch(source_branch(number))
            for controller, zone in self._zones:
                await client.watch(zone_branch(controller, zone))
        except BaseException:
            # Also on cancellation (Remote entering standby) so the socket is not leaked.
            await client.close()
            raise

        _LOG.info(
            "[%s] Connected to %s (RIO %s): %d zone(s), %d source(s)",
            self.log_id,
            config.address,
            self._rio_version,
            len(self._zones),
            len(self._sources),
        )
        self._client = client
        return client

    async def maintain_connection(self) -> None:
        """Publish the initial state, then block until the connection drops."""
        client = self._client
        if client is None:
            raise RioConnectionError("Connection not established")
        self.push_update()
        await client.wait_closed()
        raise RioConnectionError("Connection to Russound controller lost")

    async def close_connection(self) -> None:
        """Close the RIO connection and forget the (now stale) state."""
        client, self._client = self._client, None
        if client is not None:
            await client.close()
        if self._update_handle is not None:
            self._update_handle.cancel()
            self._update_handle = None
        for zone in self._zones.values():
            zone.clear()

    # =========================================================================
    # Notifications
    # =========================================================================

    def _on_notification(self, key: str, value: str | None) -> None:
        """Apply a RIO notification to the zone/source state."""
        branch, leaf = split_key(key)

        zone_id = parse_zone_branch(branch)
        if zone_id is not None:
            zone = self._zones.get(zone_id)
            if zone is not None and zone.apply(leaf, value):
                self._schedule_update()
            return

        source_id = parse_source_branch(branch)
        if source_id is not None:
            source = self._sources.get(source_id)
            if source is not None and source.apply(leaf, value):
                self._schedule_update()

    def _schedule_update(self) -> None:
        """Coalesce bursts of notifications into one entity update."""
        if self._update_handle is None:
            self._update_handle = self._loop.call_later(UPDATE_DEBOUNCE, self._flush_update)

    def _flush_update(self) -> None:
        self._update_handle = None
        self.push_update()

    # =========================================================================
    # Commands
    # =========================================================================

    def _require_client(self) -> RioClient:
        client = self._client
        if client is None or not client.connected:
            raise RioConnectionError(f"{self.log_id} is not connected")
        return client

    def _require_zone(self, controller: int, zone: int) -> ZoneState:
        state = self._zones.get((controller, zone))
        if state is None:
            raise ValueError(f"Zone C[{controller}].Z[{zone}] is not configured")
        return state

    async def _zone_event(self, controller: int, zone: int, event: str, *args: str | int) -> None:
        await self._require_client().event(zone_branch(controller, zone), event, *args)

    async def _zone_set(self, controller: int, zone: int, leaf: str, value: str | int) -> None:
        await self._require_client().set(f"{zone_branch(controller, zone)}.{leaf}", value)

    async def power_on(self, controller: int, zone: int) -> None:
        """Turn a zone on."""
        await self._zone_event(controller, zone, "ZoneOn")

    async def power_off(self, controller: int, zone: int) -> None:
        """Turn a zone off."""
        await self._zone_event(controller, zone, "ZoneOff")

    async def power_toggle(self, controller: int, zone: int) -> None:
        """Toggle a zone's power."""
        if self._require_zone(controller, zone).power:
            await self.power_off(controller, zone)
        else:
            await self.power_on(controller, zone)

    async def all_zones(self, controller: int, zone: int, turn_on: bool) -> None:
        """Turn all zones of the system on or off."""
        await self._zone_event(controller, zone, "AllOn" if turn_on else "AllOff")

    async def set_volume(self, controller: int, zone: int, volume: int) -> None:
        """Set a zone's volume, 0..50."""
        volume = max(0, min(MAX_VOLUME, int(volume)))
        await self._zone_event(controller, zone, "KeyPress", "Volume", volume)

    async def volume_up(self, controller: int, zone: int) -> None:
        """Raise a zone's volume by one step."""
        await self._zone_event(controller, zone, "KeyPress", "VolumeUp")

    async def volume_down(self, controller: int, zone: int) -> None:
        """Lower a zone's volume by one step."""
        await self._zone_event(controller, zone, "KeyPress", "VolumeDown")

    async def mute_toggle(self, controller: int, zone: int) -> None:
        """Toggle a zone's mute."""
        await self._zone_event(controller, zone, "KeyRelease", "Mute")

    async def set_mute(self, controller: int, zone: int, muted: bool) -> None:
        """Mute or unmute a zone."""
        if version_tuple(self._rio_version) >= MUTE_ON_OFF_MIN_VERSION:
            await self._zone_event(controller, zone, "ZoneMuteOn" if muted else "ZoneMuteOff")
            return
        # Older firmware only knows the mute toggle key.
        if self._require_zone(controller, zone).muted != muted:
            await self.mute_toggle(controller, zone)

    async def select_source(self, controller: int, zone: int, source: int) -> None:
        """Select the source of a zone."""
        if source not in self._sources:
            raise ValueError(f"Source {source} does not exist")
        await self._zone_event(controller, zone, "SelectSource", source)

    async def send_key(self, controller: int, zone: int, key: str) -> None:
        """Send a transport key (Play, Pause, Stop, Next, Previous) to the zone's source."""
        await self._zone_event(controller, zone, "KeyPress", key)

    async def play_pause(self, controller: int, zone: int) -> None:
        """Toggle playback of the zone's source."""
        source = self.source(self._require_zone(controller, zone).source)
        playing = source is not None and source.play_status == "playing"
        await self.send_key(controller, zone, "Pause" if playing else "Play")

    async def adjust_tone(self, controller: int, zone: int, leaf: str, delta: int) -> None:
        """Step bass, treble or balance by ``delta`` within -10..10."""
        state = self._require_zone(controller, zone)
        current = {"bass": state.bass, "treble": state.treble, "balance": state.balance}[leaf] or 0
        await self._zone_set(controller, zone, leaf, max(TONE_MIN, min(TONE_MAX, current + delta)))

    async def reset_tone(self, controller: int, zone: int) -> None:
        """Reset bass, treble and balance to 0."""
        for leaf in ("bass", "treble", "balance"):
            await self._zone_set(controller, zone, leaf, 0)

    async def set_loudness(self, controller: int, zone: int, loudness: bool | None = None) -> None:
        """Set loudness on or off; None toggles."""
        if loudness is None:
            loudness = not self._require_zone(controller, zone).loudness
        await self._zone_set(controller, zone, "loudness", "ON" if loudness else "OFF")
