"""
Media-player entity: one per Russound zone.

:copyright: (c) 2026 by Jeff Ferdinandsen.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any

import ucapi
from const import COMMAND_TIMEOUT, VOLUME_STEPS, DeviceConfig, SimpleCommands
from device import RussoundDevice
from ucapi import EntityTypes, media_player
from ucapi.media_player import Attributes, DeviceClasses
from ucapi_framework import MediaPlayerEntity, create_entity_id

_LOG = logging.getLogger(__name__)

FEATURES = [
    media_player.Features.ON_OFF,
    media_player.Features.TOGGLE,
    media_player.Features.VOLUME,
    media_player.Features.VOLUME_UP_DOWN,
    media_player.Features.MUTE,
    media_player.Features.UNMUTE,
    media_player.Features.MUTE_TOGGLE,
    media_player.Features.PLAY_PAUSE,
    media_player.Features.STOP,
    media_player.Features.NEXT,
    media_player.Features.PREVIOUS,
    media_player.Features.SELECT_SOURCE,
    media_player.Features.MEDIA_TITLE,
    media_player.Features.MEDIA_ARTIST,
    media_player.Features.MEDIA_ALBUM,
    media_player.Features.MEDIA_IMAGE_URL,
    media_player.Features.MEDIA_DURATION,
    media_player.Features.MEDIA_POSITION,
]


class RussoundZoneMediaPlayer(MediaPlayerEntity):
    """Media-player entity representing a single Russound zone."""

    def __init__(
        self,
        config_device: DeviceConfig,
        device_instance: RussoundDevice,
        sub_id: str,
    ) -> None:
        """
        Create the entity for one zone.

        :param config_device: persisted controller configuration
        :param device_instance: the shared RIO device wrapper
        :param sub_id: zone sub-device id, e.g. ``c1z3``
        """
        self._device = device_instance
        self._sub_id = sub_id

        entity_id = create_entity_id(
            EntityTypes.MEDIA_PLAYER, config_device.identifier, sub_id
        )
        zone_name = device_instance.zone_name(sub_id)

        _LOG.debug("Creating media player entity %s (%s)", entity_id, zone_name)

        super().__init__(
            entity_id,
            zone_name,
            FEATURES,
            attributes={
                Attributes.STATE: media_player.States.UNKNOWN,
                Attributes.VOLUME: 0,
                Attributes.MUTED: False,
                Attributes.SOURCE: "",
                Attributes.SOURCE_LIST: [],
            },
            device_class=DeviceClasses.SPEAKER,
            options={
                media_player.Options.VOLUME_STEPS: VOLUME_STEPS,
                media_player.Options.SIMPLE_COMMANDS: [
                    member.value for member in SimpleCommands
                ],
            },
            cmd_handler=self.handle_command,
        )

        self.subscribe_to_device(device_instance)

    async def sync_state(self) -> None:
        """Push the device's cached zone attributes to the Remote."""
        if self._device is None:
            self.set_unavailable()
            return

        attributes = self._device.get_media_player_attributes(self._sub_id)
        if attributes is not None:
            self.update(attributes)

    async def handle_command(
        self,
        _entity: MediaPlayerEntity,
        cmd_id: str,
        params: dict[str, Any] | None,
        _: Any | None = None,
    ) -> ucapi.StatusCodes:
        """
        Handle a command from the Remote for this zone.

        :param _entity: receiving entity (unused)
        :param cmd_id: command identifier
        :param params: optional command parameters
        :return: status code reported back to the Remote
        """
        if self._device is None or not self._device.is_connected:
            _LOG.warning("Command %s ignored, %s is offline", cmd_id, self._sub_id)
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE

        _LOG.info("[%s] command: %s %s", self._sub_id, cmd_id, params or "")
        zone = self._sub_id

        try:
            async with asyncio.timeout(COMMAND_TIMEOUT):
                match cmd_id:
                    case media_player.Commands.ON:
                        await self._device.zone_on(zone)
                    case media_player.Commands.OFF:
                        await self._device.zone_off(zone)
                    case media_player.Commands.TOGGLE:
                        await self._device.zone_toggle(zone)
                    case media_player.Commands.VOLUME:
                        await self._device.set_volume(zone, (params or {}).get("volume"))
                    case media_player.Commands.VOLUME_UP:
                        await self._device.volume_up(zone)
                    case media_player.Commands.VOLUME_DOWN:
                        await self._device.volume_down(zone)
                    case media_player.Commands.MUTE:
                        await self._device.mute(zone)
                    case media_player.Commands.UNMUTE:
                        await self._device.unmute(zone)
                    case media_player.Commands.MUTE_TOGGLE:
                        await self._device.mute_toggle(zone)
                    case media_player.Commands.PLAY_PAUSE:
                        await self._device.play_pause(zone)
                    case media_player.Commands.STOP:
                        await self._device.transport(zone, "stop")
                    case media_player.Commands.NEXT:
                        await self._device.transport(zone, "next")
                    case media_player.Commands.PREVIOUS:
                        await self._device.transport(zone, "previous")
                    case media_player.Commands.SEEK:
                        await self._device.seek(zone, (params or {}).get("media_position", 0))
                    case media_player.Commands.SELECT_SOURCE:
                        source = (params or {}).get("source")
                        if not await self._device.select_source(zone, source):
                            return ucapi.StatusCodes.BAD_REQUEST
                    case _:
                        if await self._device.simple_command(zone, cmd_id):
                            return ucapi.StatusCodes.OK
                        _LOG.warning("Unhandled command: %s", cmd_id)
                        return ucapi.StatusCodes.NOT_IMPLEMENTED

                return ucapi.StatusCodes.OK

        except TimeoutError:
            _LOG.error("[%s] no answer to %s, restarting the connection", zone, cmd_id)
            self._device.report_unresponsive()
            return ucapi.StatusCodes.TIMEOUT
        except asyncio.CancelledError:
            # The connection dropped while the command was waiting for its
            # reply. Only pass on a cancellation aimed at this task itself.
            task = asyncio.current_task()
            if task is not None and task.cancelling() > 0:
                raise
            _LOG.warning("[%s] connection lost during %s", zone, cmd_id)
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        except (OSError, RuntimeError, ValueError) as err:
            _LOG.error("[%s] command %s failed: %s", zone, cmd_id, err)
            return ucapi.StatusCodes.BAD_REQUEST
        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("[%s] unexpected error on %s: %s", zone, cmd_id, err)
            return ucapi.StatusCodes.SERVER_ERROR


def create_zone_entities(
    config_device: DeviceConfig, device_instance: RussoundDevice
) -> list[MediaPlayerEntity]:
    """
    Entity factory: build one media player per discovered zone.

    Passed to ``BaseIntegrationDriver`` so entities are created after the
    controller reports which zones exist.
    """
    return [
        RussoundZoneMediaPlayer(config_device, device_instance, sub_id)
        for sub_id in device_instance.zone_ids
    ]
