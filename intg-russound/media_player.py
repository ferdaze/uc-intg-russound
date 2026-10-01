"""
Media Player Entity.

One media player entity per Russound zone: power, volume, mute, source selection,
now-playing metadata (for sources that report it) and tone controls as simple commands.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from typing import Any

import ucapi
from const import SOURCE_COMMAND_PREFIX, DeviceConfig, SimpleCommands, ZoneConfig
from device import RussoundDevice
from rio import RioCommandError, RioConnectionError
from russound import MAX_VOLUME
from ucapi import EntityTypes, media_player
from ucapi.media_player import Attributes, Commands, DeviceClasses, Options, States
from ucapi_framework import MediaPlayerEntity, create_entity_id

_LOG = logging.getLogger(__name__)

FEATURES = [
    media_player.Features.ON_OFF,
    media_player.Features.TOGGLE,
    media_player.Features.VOLUME,
    media_player.Features.VOLUME_UP_DOWN,
    media_player.Features.MUTE_TOGGLE,
    media_player.Features.MUTE,
    media_player.Features.UNMUTE,
    media_player.Features.SELECT_SOURCE,
    media_player.Features.PLAY_PAUSE,
    media_player.Features.STOP,
    media_player.Features.NEXT,
    media_player.Features.PREVIOUS,
    media_player.Features.MEDIA_TITLE,
    media_player.Features.MEDIA_ARTIST,
    media_player.Features.MEDIA_ALBUM,
    media_player.Features.MEDIA_IMAGE_URL,
]

UI_VOLUME_SCALE = 100 // MAX_VOLUME
"""The Remote uses 0..100, Russound zones 0..50."""

_TRANSPORT_KEYS = {
    Commands.STOP: "Stop",
    Commands.NEXT: "Next",
    Commands.PREVIOUS: "Previous",
}


def to_ui_volume(volume: int) -> int:
    """Russound volume (0..50) -> Remote volume (0..100)."""
    return max(0, min(100, volume * UI_VOLUME_SCALE))


def to_device_volume(volume: float) -> int:
    """Remote volume (0..100) -> Russound volume (0..50)."""
    return max(0, min(MAX_VOLUME, round(float(volume) / UI_VOLUME_SCALE)))


class RussoundZoneMediaPlayer(MediaPlayerEntity):
    """Media player entity for one Russound zone."""

    def __init__(self, config_device: DeviceConfig, device_instance: RussoundDevice, zone_config: ZoneConfig):
        """
        Initialize the zone entity.

        :param config_device: Controller configuration from setup
        :param device_instance: The controller connection
        :param zone_config: The zone this entity controls
        """
        self._device = device_instance
        self._controller = zone_config.controller
        self._zone = zone_config.zone
        entity_id = create_entity_id(EntityTypes.MEDIA_PLAYER, config_device.identifier, zone_config.key)

        _LOG.debug("Initializing media player entity: %s", entity_id)

        super().__init__(
            entity_id,
            zone_config.name,
            FEATURES,
            attributes={
                Attributes.STATE: States.UNAVAILABLE,
                Attributes.VOLUME: 0,
                Attributes.MUTED: False,
                Attributes.SOURCE: "",
                Attributes.SOURCE_LIST: [],
            },
            device_class=DeviceClasses.SPEAKER,
            options={
                Options.SIMPLE_COMMANDS: [command.value for command in SimpleCommands],
                Options.VOLUME_STEPS: MAX_VOLUME,
            },
            cmd_handler=self.handle_command,
        )

        self.subscribe_to_device(device_instance)

    async def sync_state(self) -> None:
        """Push the zone's current state to the Remote."""
        zone = self._device.zone(self._controller, self._zone)
        if zone is None or not self._device.is_connected or not zone.known:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return

        source = self._device.source(zone.source)
        attrs: dict[str, Any] = {
            Attributes.STATE: self._map_state(zone.power, source.play_status if source else None),
            Attributes.SOURCE: source.name if source else "",
            Attributes.SOURCE_LIST: self._device.source_names,
        }
        if zone.volume is not None:
            attrs[Attributes.VOLUME] = to_ui_volume(zone.volume)
        if zone.muted is not None:
            attrs[Attributes.MUTED] = zone.muted

        # Empty strings (not None) so stale metadata is cleared on the Remote.
        show_media = bool(zone.power) and source is not None
        attrs[Attributes.MEDIA_TITLE] = (source.title if show_media else None) or ""
        attrs[Attributes.MEDIA_ARTIST] = (source.artist if show_media else None) or ""
        attrs[Attributes.MEDIA_ALBUM] = (source.album if show_media else None) or ""
        attrs[Attributes.MEDIA_IMAGE_URL] = (source.cover_art_url if show_media else None) or ""

        self.update(attrs)

    @staticmethod
    def _map_state(power: bool | None, play_status: str | None) -> States:
        if not power:
            return States.OFF
        if play_status == "playing":
            return States.PLAYING
        if play_status == "paused":
            return States.PAUSED
        if play_status in ("transitioning", "loading"):
            return States.BUFFERING
        return States.ON

    async def handle_command(  # pylint: disable=too-many-branches
        self,
        _entity: MediaPlayerEntity,
        cmd_id: str,
        params: dict[str, Any] | None,
        **_kwargs: Any,
    ) -> ucapi.StatusCodes:
        """
        Handle media player commands from the Remote.

        :param _entity: The entity receiving the command (unused)
        :param cmd_id: The command identifier
        :param params: Optional command parameters
        :return: Status code indicating success or failure
        """
        _LOG.info("[%s] Command: %s %s", self.id, cmd_id, params if params else "")
        device = self._device
        ctrl, zone = self._controller, self._zone

        try:
            match cmd_id:
                case Commands.ON:
                    await device.power_on(ctrl, zone)
                case Commands.OFF:
                    await device.power_off(ctrl, zone)
                case Commands.TOGGLE:
                    await device.power_toggle(ctrl, zone)
                case Commands.VOLUME:
                    if not params or "volume" not in params:
                        return ucapi.StatusCodes.BAD_REQUEST
                    await device.set_volume(ctrl, zone, to_device_volume(params["volume"]))
                case Commands.VOLUME_UP:
                    await device.volume_up(ctrl, zone)
                case Commands.VOLUME_DOWN:
                    await device.volume_down(ctrl, zone)
                case Commands.MUTE_TOGGLE:
                    await device.mute_toggle(ctrl, zone)
                case Commands.MUTE:
                    await device.set_mute(ctrl, zone, True)
                case Commands.UNMUTE:
                    await device.set_mute(ctrl, zone, False)
                case Commands.SELECT_SOURCE:
                    number = device.source_number((params or {}).get("source", ""))
                    if number is None:
                        _LOG.warning("[%s] Unknown source: %s", self.id, params)
                        return ucapi.StatusCodes.BAD_REQUEST
                    await device.select_source(ctrl, zone, number)
                case Commands.PLAY_PAUSE:
                    await device.play_pause(ctrl, zone)
                case Commands.STOP | Commands.NEXT | Commands.PREVIOUS:
                    await device.send_key(ctrl, zone, _TRANSPORT_KEYS[cmd_id])
                case _:
                    return await self._handle_simple_command(cmd_id)

            return ucapi.StatusCodes.OK

        except RioConnectionError as ex:
            _LOG.error("[%s] Controller not reachable for %s: %s", self.id, cmd_id, ex)
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        except (RioCommandError, ValueError) as ex:
            _LOG.error("[%s] Command %s rejected: %s", self.id, cmd_id, ex)
            return ucapi.StatusCodes.BAD_REQUEST

    async def _handle_simple_command(self, cmd_id: str) -> ucapi.StatusCodes:  # pylint: disable=too-many-branches
        device = self._device
        ctrl, zone = self._controller, self._zone

        match cmd_id:
            case SimpleCommands.BASS_UP:
                await device.adjust_tone(ctrl, zone, "bass", 1)
            case SimpleCommands.BASS_DOWN:
                await device.adjust_tone(ctrl, zone, "bass", -1)
            case SimpleCommands.TREBLE_UP:
                await device.adjust_tone(ctrl, zone, "treble", 1)
            case SimpleCommands.TREBLE_DOWN:
                await device.adjust_tone(ctrl, zone, "treble", -1)
            case SimpleCommands.BALANCE_LEFT:
                await device.adjust_tone(ctrl, zone, "balance", -1)
            case SimpleCommands.BALANCE_RIGHT:
                await device.adjust_tone(ctrl, zone, "balance", 1)
            case SimpleCommands.TONE_RESET:
                await device.reset_tone(ctrl, zone)
            case SimpleCommands.LOUDNESS_ON:
                await device.set_loudness(ctrl, zone, True)
            case SimpleCommands.LOUDNESS_OFF:
                await device.set_loudness(ctrl, zone, False)
            case SimpleCommands.LOUDNESS_TOGGLE:
                await device.set_loudness(ctrl, zone)
            case SimpleCommands.ALL_ZONES_ON:
                await device.all_zones(ctrl, zone, True)
            case SimpleCommands.ALL_ZONES_OFF:
                await device.all_zones(ctrl, zone, False)
            case _ if cmd_id.startswith(SOURCE_COMMAND_PREFIX):
                await device.select_source(ctrl, zone, int(cmd_id.removeprefix(SOURCE_COMMAND_PREFIX)))
            case _:
                _LOG.warning("[%s] Unhandled command: %s", self.id, cmd_id)
                return ucapi.StatusCodes.NOT_IMPLEMENTED

        return ucapi.StatusCodes.OK
