"""
Russound RIO device communication.

Wraps :mod:`aiorussound` and exposes one cached ``MediaPlayerAttributes``
object per zone.

Reconnection is owned by this module. aiorussound has its own reconnect loop,
but it only re-opens the socket: RIO ``WATCH`` subscriptions are per
connection and are not re-issued, and the library reports nothing when the
new session is up. So when a session ends, the library's loop is stopped and
a fresh client is built here, exactly as on first connect, retrying with
backoff until the controller answers or ``disconnect()`` is called. The
framework watchdog stays disabled so only one thing ever reconnects.

:copyright: (c) 2026 by Jeff Ferdinandsen.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
from asyncio import AbstractEventLoop
from typing import Any

from aiorussound import RussoundTcpConnectionHandler
from aiorussound.rio import RussoundRIOClient
from aiorussound.rio.client import ZoneControlSurface
from aiorussound.rio.models import CallbackType, PartyMode, PlayStatus, Source
from const import (
    RECONNECT_MAX_DELAY,
    RECONNECT_MIN_DELAY,
    TONE_MAX,
    TONE_MIN,
    TONE_STEP,
    DeviceConfig,
    russound_to_uc_volume,
    uc_to_russound_volume,
    zone_sub_id,
)
from ucapi import media_player
from ucapi_framework import BaseConfigManager, DeviceEvents, ExternalClientDevice
from ucapi_framework.helpers import MediaPlayerAttributes

_LOG = logging.getLogger(__name__)


class RussoundDevice(ExternalClientDevice):
    """One RIO connection to a Russound controller (and any RNET-chained controllers)."""

    def __init__(
        self,
        device_config: DeviceConfig,
        loop: AbstractEventLoop | None = None,
        config_manager: BaseConfigManager | None = None,
        driver: Any = None,
    ) -> None:
        """
        Initialize the device.

        :param device_config: persisted configuration for this controller
        :param loop: event loop
        :param config_manager: framework configuration manager
        :param driver: reference to the integration driver
        """
        super().__init__(
            device_config,
            loop,
            # Reconnection is handled by _retry_loop(); see the module docstring.
            enable_watchdog=False,
            config_manager=config_manager,
            driver=driver,
        )
        self._zone_attributes: dict[str, MediaPlayerAttributes] = {}
        self._zone_names: dict[str, str] = dict(device_config.zone_names or {})
        self._session_lock = asyncio.Lock()
        self._retry_task: asyncio.Task | None = None

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
        """Return the device address."""
        return self._device_config.address

    @property
    def log_id(self) -> str:
        """Return a short identifier for log lines."""
        return self.name or self.identifier

    @property
    def client(self) -> RussoundRIOClient | None:
        """Return the underlying RIO client, if one exists."""
        return self._client

    @property
    def zone_ids(self) -> list[str]:
        """
        Return the sub-device ids of every known zone, in controller/zone order.

        Populated once the first connection completes; falls back to the names
        cached in the device config so entities can be rebuilt after a reboot
        before the controller answers.
        """
        if self._client is not None and self._client.controllers:
            ids: list[str] = []
            for controller_id in sorted(self._client.controllers):
                controller = self._client.controllers[controller_id]
                for zone_id in sorted(controller.zones):
                    ids.append(zone_sub_id(controller_id, zone_id))
            if ids:
                return ids
        return list(self._zone_names)

    def zone_name(self, sub_id: str) -> str:
        """Return the friendly name of a zone, falling back to its sub id."""
        zone = self.zone(sub_id)
        if zone is not None and zone.name:
            return zone.name
        return self._zone_names.get(sub_id, sub_id)

    def zone(self, sub_id: str) -> ZoneControlSurface | None:
        """
        Resolve a live zone object from its sub-device id.

        aiorussound rebuilds ``ZoneControlSurface`` instances on every state
        notification, so always resolve fresh instead of holding a reference.
        """
        if self._client is None:
            return None
        try:
            controller_part, zone_part = sub_id.lstrip("c").split("z", 1)
            controller_id = int(controller_part)
            zone_id = int(zone_part)
        except (AttributeError, ValueError):
            _LOG.warning("[%s] Malformed zone id: %s", self.log_id, sub_id)
            return None

        controller = self._client.controllers.get(controller_id)
        if controller is None:
            return None
        return controller.zones.get(zone_id)

    def get_media_player_attributes(self, sub_id: str) -> MediaPlayerAttributes | None:
        """
        Return the cached attributes for a zone.

        Called by each media-player entity from ``sync_state()``.
        """
        return self._zone_attributes.get(sub_id)

    # =========================================================================
    # Connection management (ExternalClientDevice contract)
    # =========================================================================

    async def connect(self) -> bool:
        """
        Open the RIO session.

        If the controller cannot be reached, a background retry keeps trying
        until it answers or ``disconnect()`` is called.

        :return: True when the session is up, False if it is still being retried
        """
        if self.is_connected:
            return True
        if self._retrying():
            _LOG.debug("[%s] Already retrying in the background", self.log_id)
            return False

        self.events.emit(DeviceEvents.CONNECTING, self.identifier)
        if await self._open_session():
            return True

        self.events.emit(DeviceEvents.ERROR, self.identifier, "Controller not reachable")
        self._start_retry()
        return False

    async def disconnect(self) -> None:
        """Close the RIO session and stop any background retry."""
        await self._stop_retry()
        async with self._session_lock:
            await super().disconnect()

    async def create_client(self) -> RussoundRIOClient:
        """Create the RIO client. Must run inside the event loop."""
        handler = RussoundTcpConnectionHandler(
            self._device_config.address, self._device_config.port
        )
        return RussoundRIOClient(handler)

    async def connect_client(self) -> None:
        """Open the RIO session, load metadata and subscribe to notifications."""
        await self._client.connect()
        await self._client.register_state_update_callbacks(self._on_client_update)
        await self._load_metadata()

    async def disconnect_client(self) -> None:
        """Tear the RIO session down, including the library's reconnect loop."""
        client: RussoundRIOClient | None = self._client
        if client is None:
            return

        client.unregister_state_update_callbacks(self._on_client_update)
        await client.disconnect()

        # aiorussound only cancels its connect task when it is currently
        # connected. If we disconnect mid-backoff the reconnect loop survives,
        # so cancel it explicitly.
        reconnect_task = getattr(client, "_reconnect_task", None)
        if (
            reconnect_task is not None
            and not reconnect_task.done()
            and reconnect_task is not asyncio.current_task()
        ):
            reconnect_task.cancel()
            try:
                await reconnect_task
            except (asyncio.CancelledError, Exception):  # pylint: disable=broad-except
                pass

        # aiorussound never closes its socket. Left open, every reconnect
        # would leave another dead session behind on the controller.
        writer = client.connection_handler.writer
        if writer is not None:
            client.connection_handler.writer = None
            writer.close()
            try:
                async with asyncio.timeout(2):
                    await writer.wait_closed()
            except (OSError, TimeoutError):
                pass

    def check_client_connected(self) -> bool:
        """Return True while the RIO session is established."""
        return self._client is not None and self._client.is_connected()

    def report_unresponsive(self) -> None:
        """
        Restart the session after the controller failed to answer a command.

        aiorussound matches replies to requests by order, so one lost reply
        leaves every later reply paired with the wrong request. A fresh
        session is the only safe way out.
        """
        self._handle_session_lost("controller stopped answering")

    async def _open_session(self) -> bool:
        """
        Build a fresh client, connect it and subscribe to all zones and sources.

        :return: True if the session is up
        """
        async with self._session_lock:
            if self.is_connected:
                return True

            await self._cleanup_client()
            error: str | None = None
            try:
                self._client = await self.create_client()
                await self.connect_client()
                if not self.check_client_connected():
                    error = "connection lost while loading zones"
            except asyncio.CancelledError:
                # aiorussound cancels its pending requests when the socket
                # drops, which surfaces here as CancelledError even though
                # nobody cancelled this task. Only pass on a real cancellation.
                if _cancel_requested():
                    raise
                error = "connection lost while loading zones"
            except Exception as err:  # pylint: disable=broad-except
                error = str(err) or type(err).__name__

            if error is not None:
                _LOG.warning(
                    "[%s] Could not connect to %s:%s - %s",
                    self.log_id,
                    self._device_config.address,
                    self._device_config.port,
                    error,
                )
                await self._cleanup_client()
                self._is_connected = False
                return False

            self._is_connected = True

        _LOG.info("[%s] Connected", self.log_id)
        self.events.emit(DeviceEvents.CONNECTED, self.identifier)
        self.push_update()
        return True

    def _handle_session_lost(self, reason: str) -> None:
        """Mark the session as down and start reconnecting in the background."""
        client: RussoundRIOClient | None = self._client
        if client is not None:
            # Stop aiorussound's own reconnect loop; see the module docstring.
            client._attempt_reconnection = False  # pylint: disable=protected-access

        if self._is_connected:
            _LOG.warning("[%s] Disconnected: %s", self.log_id, reason)
            self._is_connected = False
            self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)

        self._start_retry()

    def _retrying(self) -> bool:
        """Return True while the background retry is running."""
        return self._retry_task is not None and not self._retry_task.done()

    def _start_retry(self) -> None:
        """Start the background retry unless it is already running."""
        if not self._retrying():
            self._retry_task = asyncio.create_task(self._retry_loop())

    async def _stop_retry(self) -> None:
        """Cancel the background retry and wait for it to finish."""
        task, self._retry_task = self._retry_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _retry_loop(self) -> None:
        """Reconnect with exponential backoff until the session is up."""
        delay = RECONNECT_MIN_DELAY
        attempt = 0
        while True:
            await asyncio.sleep(delay)
            attempt += 1
            _LOG.info("[%s] Reconnect attempt %d", self.log_id, attempt)
            if await self._open_session():
                return
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _load_metadata(self) -> None:
        """Fetch zone/source metadata and start RIO WATCH subscriptions."""
        await self._client.load_zone_source_metadata()
        self._refresh_attributes()
        self._cache_zone_names()
        _LOG.info(
            "[%s] Loaded %d zone(s) and %d source(s)",
            self.log_id,
            len(self.zone_ids),
            len(self._client.sources) if self._client else 0,
        )

    async def _on_client_update(
        self, client: RussoundRIOClient, callback_type: CallbackType
    ) -> None:
        """
        Handle a state or connection callback from aiorussound.

        :param client: the emitting client
        :param callback_type: STATE for value changes, CONNECTION when a session ends
        """
        if client is not self._client:
            return

        if callback_type == CallbackType.CONNECTION:
            # aiorussound only raises this after a session has ended. It is
            # awaited from inside the library's reconnect loop, so the actual
            # reconnect is handed to a separate task.
            self._handle_session_lost("connection to the controller was lost")
            return

        self._refresh_attributes()
        self.push_update()

    # =========================================================================
    # State mapping
    # =========================================================================

    def _cache_zone_names(self) -> None:
        """Persist zone names so entities survive a Remote restart."""
        names = {sub_id: self.zone_name(sub_id) for sub_id in self.zone_ids}
        if not names or names == self._zone_names:
            return
        self._zone_names = names
        self.update_config(zone_names=names)

    def _source_for_zone(self, zone: ZoneControlSurface) -> Source | None:
        """Return the Source object currently selected by a zone."""
        if self._client is None:
            return None
        return self._client.sources.get(zone.current_source)

    def _source_list(self, zone: ZoneControlSurface) -> list[str]:
        """
        Return the source names selectable in a zone.

        Honours RIO zone/source exclusion when the controller reports it.
        """
        if self._client is None:
            return []
        allowed = zone.enabled_sources or list(self._client.sources)
        names = []
        for source_id in sorted(allowed):
            source = self._client.sources.get(source_id)
            if source and source.name:
                names.append(source.name)
        return names

    @staticmethod
    def _zone_state(
        zone: ZoneControlSurface, source: Source | None
    ) -> media_player.States:
        """Derive the media-player state from zone power and source transport."""
        if not zone.status:
            return media_player.States.OFF
        if source is not None:
            match source.play_status:
                case PlayStatus.PLAYING:
                    return media_player.States.PLAYING
                case PlayStatus.PAUSED:
                    return media_player.States.PAUSED
                case PlayStatus.LOADING | PlayStatus.TRANSITIONING:
                    return media_player.States.BUFFERING
        return media_player.States.ON

    def _refresh_attributes(self) -> None:
        """Rebuild the cached attribute set for every zone."""
        if self._client is None:
            return

        for sub_id in self.zone_ids:
            zone = self.zone(sub_id)
            if zone is None:
                continue
            source = self._source_for_zone(zone)

            attributes = MediaPlayerAttributes(
                STATE=self._zone_state(zone, source),
                VOLUME=russound_to_uc_volume(zone.volume),
                MUTED=zone.is_mute,
                SOURCE=source.name if source else "",
                SOURCE_LIST=self._source_list(zone),
            )

            if source is not None:
                attributes.MEDIA_TITLE = source.song_name or source.channel_name or ""
                attributes.MEDIA_ARTIST = source.artist_name or ""
                attributes.MEDIA_ALBUM = source.album_name or ""
                attributes.MEDIA_IMAGE_URL = source.cover_art_url or ""
                attributes.MEDIA_DURATION = source.track_time or 0
                attributes.MEDIA_POSITION = source.play_time or 0
                attributes.SHUFFLE = source.shuffle_mode

            self._zone_attributes[sub_id] = attributes

    # =========================================================================
    # Zone commands
    # =========================================================================

    async def zone_on(self, sub_id: str) -> None:
        """Turn a zone on."""
        await self._zone_call(sub_id, "zone_on")

    async def zone_off(self, sub_id: str) -> None:
        """Turn a zone off."""
        await self._zone_call(sub_id, "zone_off")

    async def zone_toggle(self, sub_id: str) -> None:
        """Toggle a zone's power state."""
        zone = self.zone(sub_id)
        if zone is None:
            return
        await self.zone_off(sub_id) if zone.status else await self.zone_on(sub_id)

    async def set_volume(self, sub_id: str, volume: Any) -> None:
        """Set absolute zone volume from a Remote 0..100 value."""
        zone = self.zone(sub_id)
        if zone is None:
            return
        await zone.set_volume(str(uc_to_russound_volume(volume)))

    async def volume_up(self, sub_id: str) -> None:
        """Raise zone volume by one RIO step."""
        await self._zone_call(sub_id, "volume_up")

    async def volume_down(self, sub_id: str) -> None:
        """Lower zone volume by one RIO step."""
        await self._zone_call(sub_id, "volume_down")

    async def mute(self, sub_id: str) -> None:
        """Mute a zone."""
        await self._zone_call(sub_id, "mute")

    async def unmute(self, sub_id: str) -> None:
        """Unmute a zone."""
        await self._zone_call(sub_id, "unmute")

    async def mute_toggle(self, sub_id: str) -> None:
        """Toggle a zone's mute state."""
        await self._zone_call(sub_id, "toggle_mute")

    async def select_source(self, sub_id: str, source_name: str | None) -> bool:
        """
        Select a source in a zone by its friendly name.

        :return: True if a matching source was found and sent
        """
        zone = self.zone(sub_id)
        if zone is None or self._client is None or not source_name:
            return False
        for source_id, source in self._client.sources.items():
            if source.name == source_name:
                await zone.select_source(source_id)
                return True
        _LOG.warning("[%s] Unknown source '%s' for %s", self.log_id, source_name, sub_id)
        return False

    async def transport(self, sub_id: str, action: str) -> None:
        """Send a transport command (play/pause/stop/next/previous) to a zone."""
        await self._zone_call(sub_id, action)

    async def play_pause(self, sub_id: str) -> None:
        """Toggle play/pause based on the current source transport state."""
        zone = self.zone(sub_id)
        if zone is None:
            return
        source = self._source_for_zone(zone)
        if source is not None and source.play_status == PlayStatus.PLAYING:
            await zone.pause()
        else:
            await zone.play()

    async def seek(self, sub_id: str, position: Any) -> None:
        """Seek the current source to an absolute position in seconds."""
        zone = self.zone(sub_id)
        if zone is None:
            return
        await zone.set_seek_time(int(position))

    async def simple_command(self, sub_id: str, command: str) -> bool:
        """
        Execute one of the extra per-zone commands.

        :return: True if the command was recognised
        """
        zone = self.zone(sub_id)
        if zone is None:
            return False

        match command:
            case "PARTY_MODE_ON":
                await zone.set_party_mode(PartyMode.ON)
            case "PARTY_MODE_MASTER":
                await zone.set_party_mode(PartyMode.MASTER)
            case "PARTY_MODE_OFF":
                await zone.set_party_mode(PartyMode.OFF)
            case "DO_NOT_DISTURB_ON":
                await zone.send_event("DoNotDisturb", "ON")
            case "DO_NOT_DISTURB_OFF":
                await zone.send_event("DoNotDisturb", "OFF")
            case "LOUDNESS_ON":
                await zone.set_loudness(True)
            case "LOUDNESS_OFF":
                await zone.set_loudness(False)
            case "BASS_UP":
                await zone.set_bass(_step(zone.bass, TONE_STEP))
            case "BASS_DOWN":
                await zone.set_bass(_step(zone.bass, -TONE_STEP))
            case "BASS_FLAT":
                await zone.set_bass(0)
            case "TREBLE_UP":
                await zone.set_treble(_step(zone.treble, TONE_STEP))
            case "TREBLE_DOWN":
                await zone.set_treble(_step(zone.treble, -TONE_STEP))
            case "TREBLE_FLAT":
                await zone.set_treble(0)
            case "BALANCE_LEFT":
                await zone.set_balance(_step(zone.balance, -TONE_STEP))
            case "BALANCE_RIGHT":
                await zone.set_balance(_step(zone.balance, TONE_STEP))
            case "BALANCE_CENTER":
                await zone.set_balance(0)
            case "ALL_ZONES_OFF":
                await zone.send_event("AllOff")
            case _ if command.startswith("PRESET_"):
                await zone.restore_preset(int(command.rsplit("_", 1)[1]))
            case _:
                return False
        return True

    async def _zone_call(self, sub_id: str, method: str) -> None:
        """Invoke a no-argument coroutine on a zone, if the zone exists."""
        zone = self.zone(sub_id)
        if zone is None:
            _LOG.warning("[%s] Zone %s not available for %s", self.log_id, sub_id, method)
            return
        await getattr(zone, method)()


def _step(current: int | None, delta: int) -> int:
    """Clamp a tone adjustment to the RIO -10..10 range."""
    return max(TONE_MIN, min(TONE_MAX, (current or 0) + delta))


def _cancel_requested() -> bool:
    """Return True if the current task is really being cancelled."""
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0
