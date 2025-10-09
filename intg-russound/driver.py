"""Russound Integration for Unfolded Circle Remote."""
import asyncio
import logging
import os
from typing import Any

import ucapi
from ucapi import IntegrationAPI, StatusCodes
from ucapi.media_player import Attributes, Commands, Features, MediaPlayer, States

from config import RussoundConfig
from const import DRIVER_ID, DRIVER_VERSION
from russound import RussoundDevice

_LOG = logging.getLogger(__name__)

# Create event loop and API instance at module level (required for decorators)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
api: IntegrationAPI = IntegrationAPI(loop)

# Global instances
config_manager: RussoundConfig = None
russound_device: RussoundDevice = None
zones: dict = {}


async def on_zone_update(zone_data: dict) -> None:
    """Handle zone state updates."""
    zone_id = zone_data.get("zone_id")
    entity_id = f"zone_{zone_id}"
    
    if entity_id not in api.configured_entities.entities:
        return
    
    attributes = {}
    
    # Map state
    if zone_data.get("power"):
        attributes[Attributes.STATE] = States.PLAYING
    else:
        attributes[Attributes.STATE] = States.OFF
    
    # Map volume (0-50 to 0-100)
    volume = zone_data.get("volume", 0)
    attributes[Attributes.VOLUME] = int((volume / 50) * 100)
    
    # Map mute
    attributes[Attributes.MUTED] = zone_data.get("mute", False)
    
    # Map source
    if zone_data.get("source_name"):
        attributes[Attributes.SOURCE] = zone_data["source_name"]
    
    # Media metadata
    if zone_data.get("media_title"):
        attributes[Attributes.MEDIA_TITLE] = zone_data["media_title"]
    if zone_data.get("media_artist"):
        attributes[Attributes.MEDIA_ARTIST] = zone_data["media_artist"]
    if zone_data.get("media_album"):
        attributes[Attributes.MEDIA_ALBUM] = zone_data["media_album"]
    
    api.configured_entities.update_attributes(entity_id, attributes)


async def on_connection_change(connected: bool) -> None:
    """Handle connection state changes."""
    state = ucapi.DeviceStates.CONNECTED if connected else ucapi.DeviceStates.DISCONNECTED
    api.set_device_state(state)
    
    if not connected and russound_device:
        await russound_device.start_reconnect()


def create_zone_entity(zone_id: int, zone_name: str = None) -> MediaPlayer:
    """Create media player entity for zone."""
    entity_id = f"zone_{zone_id}"
    name = zone_name or f"Zone {zone_id}"
    
    features = [
        Features.ON_OFF,
        Features.VOLUME,
        Features.VOLUME_UP_DOWN,
        Features.MUTE_TOGGLE,
        Features.SELECT_SOURCE,
    ]
    
    # Get source list
    source_list = []
    if russound_device:
        sources = russound_device.get_sources()
        source_list = [s.get("name", f"Source {i+1}") for i, s in enumerate(sources)]
    
    if not source_list:
        source_list = [f"Source {i+1}" for i in range(8)]
    
    attributes = {
        Attributes.STATE: States.OFF,
        Attributes.VOLUME: 0,
        Attributes.MUTED: False,
        Attributes.SOURCE: source_list[0] if source_list else "Source 1",
        Attributes.SOURCE_LIST: source_list,
    }
    
    entity = MediaPlayer(
        identifier=entity_id,
        name={"en": name},
        features=features,
        attributes=attributes,
        cmd_handler=handle_entity_command,
    )
    
    return entity


@api.listens_to(ucapi.Events.CONNECT)
async def on_connect() -> None:
    """Handle Remote connection."""
    _LOG.info("Remote connected")
    
    if config_manager and config_manager.is_configured:
        await connect_russound()


@api.listens_to(ucapi.Events.DISCONNECT)
async def on_disconnect() -> None:
    """Handle Remote disconnection."""
    _LOG.info("Remote disconnected")


@api.listens_to(ucapi.Events.ENTER_STANDBY)
async def on_standby() -> None:
    """Handle Remote standby."""
    _LOG.info("Remote entering standby")


@api.listens_to(ucapi.Events.EXIT_STANDBY)
async def on_exit_standby() -> None:
    """Handle Remote wake."""
    _LOG.info("Remote exiting standby")
    
    if russound_device and not russound_device.is_connected:
        await russound_device.start_reconnect()


@api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
async def on_subscribe_entities(entity_ids: list[str]) -> None:
    """Handle entity subscription."""
    _LOG.info(f"Subscribed to: {entity_ids}")
    
    # Update all subscribed zones
    if russound_device and russound_device.is_connected:
        for entity_id in entity_ids:
            zone_id = int(entity_id.split("_")[1])
            zone_state = await russound_device.get_zone_state(zone_id)
            if zone_state:
                await on_zone_update(zone_state)


@api.listens_to(ucapi.Events.UNSUBSCRIBE_ENTITIES)
async def on_unsubscribe_entities(entity_ids: list[str]) -> None:
    """Handle entity unsubscription."""
    _LOG.info(f"Unsubscribed from: {entity_ids}")


async def connect_russound() -> bool:
    """Connect to Russound device."""
    global russound_device
    
    if not config_manager or not config_manager.is_configured:
        _LOG.error("Not configured")
        return False
    
    try:
        russound_device = RussoundDevice(
            host=config_manager.host,
            port=config_manager.port,
            controller_id=config_manager.controller_id,
            on_update=on_zone_update,
            on_connection_change=on_connection_change,
        )
        
        api.set_device_state(ucapi.DeviceStates.CONNECTING)
        
        if await russound_device.connect():
            await create_entities()
            return True
        else:
            api.set_device_state(ucapi.DeviceStates.ERROR)
            return False
            
    except Exception as e:
        _LOG.exception(f"Connection failed: {e}")
        api.set_device_state(ucapi.DeviceStates.ERROR)
        return False


async def create_entities() -> None:
    """Create zone entities."""
    _LOG.info("Creating zone entities")
    api.available_entities.clear()
    
    for zone_id in range(1, config_manager.zones + 1):
        zone_info = await russound_device.get_zone_info(zone_id)
        zone_name = zone_info.get("name") if zone_info else None
        
        entity = create_zone_entity(zone_id, zone_name)
        api.available_entities.add(entity)
        zones[entity.id] = zone_id


async def handle_entity_command(
    entity: MediaPlayer,
    cmd_id: str,
    params: dict[str, Any] | None
) -> StatusCodes:
    """Handle entity commands."""
    _LOG.info(f"Command {cmd_id} for {entity.id}, params: {params}")
    
    zone_id = zones.get(entity.id)
    if not zone_id:
        return StatusCodes.NOT_FOUND
    
    if not russound_device or not russound_device.is_connected:
        return StatusCodes.SERVICE_UNAVAILABLE
    
    try:
        if cmd_id == Commands.ON:
            await russound_device.zone_on(zone_id)
            
        elif cmd_id == Commands.OFF:
            await russound_device.zone_off(zone_id)
            
        elif cmd_id == Commands.VOLUME:
            # Convert 0-100 to 0-50
            volume = params.get(Attributes.VOLUME, 0) if params else 0
            russound_vol = int((volume / 100) * 50)
            await russound_device.set_volume(zone_id, russound_vol)
            
        elif cmd_id == Commands.VOLUME_UP:
            await russound_device.volume_up(zone_id)
            
        elif cmd_id == Commands.VOLUME_DOWN:
            await russound_device.volume_down(zone_id)
            
        elif cmd_id == Commands.MUTE_TOGGLE:
            await russound_device.mute_toggle(zone_id)
            
        elif cmd_id == Commands.SELECT_SOURCE:
            source_name = params.get(Attributes.SOURCE) if params else None
            if source_name:
                source_id = russound_device.get_source_id_by_name(source_name)
                if source_id:
                    await russound_device.select_source(zone_id, source_id)
                else:
                    return StatusCodes.BAD_REQUEST
        else:
            return StatusCodes.NOT_IMPLEMENTED
        
        return StatusCodes.OK
        
    except Exception as e:
        _LOG.exception(f"Command failed: {e}")
        return StatusCodes.SERVER_ERROR


async def on_setup_driver(msg: ucapi.SetupDriver) -> ucapi.SetupAction:
    """Handle driver setup."""
    _LOG.info("Setup requested")
    
    setup_data = msg.setup_data or {}
    
    # Validate
    is_valid, error = config_manager.validate(setup_data)
    if not is_valid:
        _LOG.error(f"Invalid config: {error}")
        return ucapi.SetupError(error_type=ucapi.IntegrationSetupError.OTHER)
    
    # Test connection
    try:
        test_device = RussoundDevice(
            host=setup_data["host"],
            port=setup_data.get("port", 9621),
            controller_id=setup_data.get("controller_id", 1),
        )
        
        if not await test_device.connect():
            return ucapi.SetupError(
                error_type=ucapi.IntegrationSetupError.CONNECTION_REFUSED
            )
        
        await test_device.disconnect()
        
        # Save config
        config_manager.save(setup_data)
        
        # Connect
        await connect_russound()
        
        return ucapi.SetupComplete()
        
    except Exception as e:
        _LOG.exception(f"Setup failed: {e}")
        return ucapi.SetupError(error_type=ucapi.IntegrationSetupError.OTHER)


async def main():
    """Main entry point."""
    global config_manager
    
    logging.basicConfig(
        level=logging.DEBUG if os.getenv("UC_LOG_LEVEL") == "DEBUG" else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    
    _LOG.info(f"Starting Russound integration v{DRIVER_VERSION}")
    
    # Initialize config
    config_dir = os.getenv("UC_CONFIG_HOME", ".")
    config_manager = RussoundConfig(config_dir)
    
    # Start API with setup handler
    await api.init("driver.json", setup_handler=on_setup_driver)
    
    # Keep running forever
    _LOG.info("Integration driver running")
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour intervals
    except KeyboardInterrupt:
        _LOG.info("Shutting down")
    finally:
        if russound_device:
            await russound_device.disconnect()


if __name__ == "__main__":
    try:
        loop.run_until_complete(main())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
