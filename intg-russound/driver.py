"""Main driver for Russound integration."""
import asyncio
import logging
import os
from typing import Any

import ucapi
from ucapi import StatusCodes
from ucapi.media_player import Attributes, Features, MediaPlayer, States

from config import RussoundConfig
from const import (
    DRIVER_ID,
    DRIVER_VERSION,
    CONF_HOST,
    CONF_PORT,
    CONF_CONTROLLER_ID,
    CONF_ZONES,
    DEFAULT_PORT,
    DEFAULT_CONTROLLER_ID,
    DEFAULT_ZONES,
    MIN_VOLUME,
    MAX_VOLUME,
)
from russound import RussoundDevice

_LOG = logging.getLogger("driver")

# Global instances
api = ucapi.IntegrationAPI(os.getenv("UC_CONFIG_HOME", "."))
config_manager: RussoundConfig = None
russound: RussoundDevice = None


async def on_zone_update(zone) -> None:
    """Handle zone state update from Russound device.
    
    Args:
        zone: Zone object with updated state
    """
    entity_id = f"zone_{zone.zone_id}"
    
    if entity_id not in api.configured_entities.entities:
        return
    
    # Build attributes dictionary
    attributes = {}
    
    # State
    if zone.status:
        attributes[Attributes.STATE] = States.ON if zone.status == "ON" else States.OFF
    else:
        attributes[Attributes.STATE] = States.OFF
    
    # Volume (convert from Russound 0-50 to UI 0-100)
    if hasattr(zone, 'volume') and zone.volume is not None:
        attributes[Attributes.VOLUME] = russound.volume_to_ui(zone.volume)
    
    # Mute
    if hasattr(zone, 'mute') and zone.mute is not None:
        attributes[Attributes.MUTED] = zone.mute == "ON"
    
    # Source
    if hasattr(zone, 'current_source') and zone.current_source:
        source_id = int(zone.current_source)
        source = russound.get_source(source_id)
        if source and hasattr(source, 'name'):
            attributes[Attributes.SOURCE] = source.name
        else:
            attributes[Attributes.SOURCE] = f"Source {source_id}"
        
        # Media metadata if available
        if source:
            if hasattr(source, 'song_name') and source.song_name:
                attributes[Attributes.MEDIA_TITLE] = source.song_name
            if hasattr(source, 'artist_name') and source.artist_name:
                attributes[Attributes.MEDIA_ARTIST] = source.artist_name
            if hasattr(source, 'album_name') and source.album_name:
                attributes[Attributes.MEDIA_ALBUM] = source.album_name
            if hasattr(source, 'cover_art_url') and source.cover_art_url:
                attributes[Attributes.MEDIA_IMAGE_URL] = source.cover_art_url
    
    # Update entity
    _LOG.debug("Updating zone %s with attributes: %s", zone.zone_id, attributes)
    api.configured_entities.update_attributes(entity_id, attributes)


async def on_connection_change(connected: bool) -> None:
    """Handle connection state change.
    
    Args:
        connected: True if connected, False if disconnected
    """
    state = ucapi.DeviceStates.CONNECTED if connected else ucapi.DeviceStates.DISCONNECTED
    _LOG.info("Connection state changed: %s", state)
    api.set_device_state(state)
    
    if not connected:
        # Start reconnection
        await russound.start_reconnect()


def create_zone_entity(zone_id: int, zone_name: str = None) -> MediaPlayer:
    """Create media player entity for a zone.
    
    Args:
        zone_id: Zone ID (1-8)
        zone_name: Optional zone name
        
    Returns:
        MediaPlayer entity
    """
    entity_id = f"zone_{zone_id}"
    name = zone_name or f"Zone {zone_id}"
    
    # Define features
    features = [
        Features.ON_OFF,
        Features.VOLUME,
        Features.VOLUME_UP_DOWN,
        Features.MUTE_TOGGLE,
        Features.SELECT_SOURCE,
        Features.MEDIA_TITLE,
        Features.MEDIA_ARTIST,
        Features.MEDIA_ALBUM,
        Features.MEDIA_IMAGE_URL,
    ]
    
    # Get source list
    source_list = []
    if russound and russound.is_connected:
        for i in range(1, 9):  # MCA-88 has 8 sources
            source = russound.get_source(i)
            if source and hasattr(source, 'name') and source.name:
                source_list.append(source.name)
            else:
                source_list.append(f"Source {i}")
    else:
        # Default source list
        source_list = [f"Source {i}" for i in range(1, 9)]
    
    # Initial attributes
    attributes = {
        Attributes.STATE: States.OFF,
        Attributes.VOLUME: 0,
        Attributes.MUTED: False,
        Attributes.SOURCE: source_list[0],
        Attributes.SOURCE_LIST: source_list,
    }
    
    # Create entity
    entity = MediaPlayer(
        identifier=entity_id,
        name={"en": name},
        features=features,
        attributes=attributes,
        options={
            "volume_steps": 50,  # Match Russound's granularity
        }
    )
    
    return entity


@api.listens_to(ucapi.Events.CONNECT)
async def on_connect() -> None:
    """Handle connection from Remote."""
    _LOG.info("Remote connected")
    
    if config_manager.is_configured:
        # Connect to Russound device
        await connect_russound()


@api.listens_to(ucapi.Events.DISCONNECT)
async def on_disconnect() -> None:
    """Handle disconnection from Remote."""
    _LOG.info("Remote disconnected")


@api.listens_to(ucapi.Events.ENTER_STANDBY)
async def on_standby() -> None:
    """Handle Remote entering standby."""
    _LOG.info("Remote entering standby")
    # Keep connection alive but stop reconnect attempts


@api.listens_to(ucapi.Events.EXIT_STANDBY)
async def on_exit_standby() -> None:
    """Handle Remote exiting standby."""
    _LOG.info("Remote exiting standby")
    # Resume reconnect if disconnected
    if russound and not russound.is_connected:
        await russound.start_reconnect()


@api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
async def on_subscribe_entities(entity_ids: list[str]) -> None:
    """Handle entity subscription.
    
    Args:
        entity_ids: List of entity IDs to subscribe to
    """
    _LOG.info("Subscribed to entities: %s", entity_ids)
    
    # Update all subscribed entities with current state
    if russound and russound.is_connected:
        for entity_id in entity_ids:
            zone_id = int(entity_id.split("_")[1])
            zone = russound.get_zone(zone_id)
            if zone:
                await on_zone_update(zone)


@api.listens_to(ucapi.Events.UNSUBSCRIBE_ENTITIES)
async def on_unsubscribe_entities(entity_ids: list[str]) -> None:
    """Handle entity unsubscription.
    
    Args:
        entity_ids: List of entity IDs to unsubscribe from
    """
    _LOG.info("Unsubscribed from entities: %s", entity_ids)


async def connect_russound() -> bool:
    """Connect to Russound device.
    
    Returns:
        True if successful, False otherwise
    """
    global russound
    
    if not config_manager.is_configured:
        _LOG.error("Integration not configured")
        return False
    
    try:
        # Create Russound device handler
        russound = RussoundDevice(
            host=config_manager.host,
            port=config_manager.port,
            controller_id=config_manager.controller_id,
            on_update=on_zone_update,
            on_connection_change=on_connection_change,
        )
        
        # Connect
        api.set_device_state(ucapi.DeviceStates.CONNECTING)
        success = await russound.connect()
        
        if success:
            _LOG.info("Successfully connected to Russound")
            
            # Create entities for all zones
            await create_entities()
            
            return True
        else:
            _LOG.error("Failed to connect to Russound")
            api.set_device_state(ucapi.DeviceStates.ERROR)
            return False
            
    except Exception as e:
        _LOG.exception("Error connecting to Russound: %s", e)
        api.set_device_state(ucapi.DeviceStates.ERROR)
        return False


async def create_entities() -> None:
    """Create media player entities for all zones."""
    _LOG.info("Creating zone entities")
    
    # Clear existing entities
    api.available_entities.clear()
    
    # Create entity for each zone
    for zone_id in range(1, config_manager.zones + 1):
        zone = russound.get_zone(zone_id)
        zone_name = None
        
        if zone and hasattr(zone, 'name') and zone.name:
            zone_name = zone.name
        
        entity = create_zone_entity(zone_id, zone_name)
        api.available_entities.add(entity)
        _LOG.info("Created entity for zone %s: %s", zone_id, entity.name)


@api.listens_to(ucapi.Events.ENTITY_COMMAND)
async def on_entity_command(
    entity: MediaPlayer,
    cmd_id: str,
    params: dict[str, Any] | None
) -> StatusCodes:
    """Handle entity command from Remote.
    
    Args:
        entity: Target entity
        cmd_id: Command ID
        params: Command parameters
        
    Returns:
        Status code
    """
    _LOG.info("Command %s for entity %s with params %s", cmd_id, entity.id, params)
    
    # Extract zone ID from entity ID
    zone_id = int(entity.id.split("_")[1])
    
    if not russound or not russound.is_connected:
        _LOG.error("Not connected to Russound device")
        return StatusCodes.SERVICE_UNAVAILABLE
    
    try:
        # Handle command
        if cmd_id == ucapi.media_player.Commands.ON:
            success = await russound.zone_on(zone_id)
            
        elif cmd_id == ucapi.media_player.Commands.OFF:
            success = await russound.zone_off(zone_id)
            
        elif cmd_id == ucapi.media_player.Commands.VOLUME:
            volume = params.get("volume", 0) if params else 0
            success = await russound.set_volume(zone_id, volume)
            
        elif cmd_id == ucapi.media_player.Commands.VOLUME_UP:
            success = await russound.volume_up(zone_id)
            
        elif cmd_id == ucapi.media_player.Commands.VOLUME_DOWN:
            success = await russound.volume_down(zone_id)
            
        elif cmd_id == ucapi.media_player.Commands.MUTE_TOGGLE:
            success = await russound.mute_on(zone_id)
            
        elif cmd_id == ucapi.media_player.Commands.SELECT_SOURCE:
            source_name = params.get("source") if params else None
            if source_name:
                # Find source ID by name
                source_id = None
                for i in range(1, 9):
                    source = russound.get_source(i)
                    if source and hasattr(source, 'name') and source.name == source_name:
                        source_id = i
                        break
                
                if source_id:
                    success = await russound.select_source(zone_id, source_id)
                else:
                    _LOG.error("Source not found: %s", source_name)
                    return StatusCodes.BAD_REQUEST
            else:
                return StatusCodes.BAD_REQUEST
        
        else:
            _LOG.warning("Unsupported command: %s", cmd_id)
            return StatusCodes.NOT_IMPLEMENTED
        
        return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
        
    except Exception as e:
        _LOG.exception("Error handling command: %s", e)
        return StatusCodes.SERVER_ERROR


@api.listens_to(ucapi.Events.SETUP_DRIVER)
async def on_setup_driver(msg: ucapi.SetupDriver) -> ucapi.SetupAction:
    """Handle driver setup flow.
    
    Args:
        msg: Setup driver message
        
    Returns:
        Setup action
    """
    _LOG.info("Setup driver request received")
    
    # Get setup data
    setup_data = msg.setup_data or {}
    
    # Validate configuration
    is_valid, error = config_manager.validate(setup_data)
    
    if not is_valid:
        _LOG.error("Invalid configuration: %s", error)
        return ucapi.SetupError(error_type=ucapi.IntegrationSetupError.OTHER)
    
    # Test connection
    _LOG.info("Testing connection to Russound at %s:%s",
              setup_data.get(CONF_HOST),
              setup_data.get(CONF_PORT, DEFAULT_PORT))
    
    try:
        # Create temporary connection to test
        test_device = RussoundDevice(
            host=setup_data[CONF_HOST],
            port=setup_data.get(CONF_PORT, DEFAULT_PORT),
            controller_id=setup_data.get(CONF_CONTROLLER_ID, DEFAULT_CONTROLLER_ID),
        )
        
        success = await test_device.connect()
        await test_device.disconnect()
        
        if not success:
            _LOG.error("Failed to connect to Russound device")
            return ucapi.SetupError(error_type=ucapi.IntegrationSetupError.CONNECTION_REFUSED)
        
        # Save configuration
        config_manager.save(setup_data)
        
        # Connect to device
        await connect_russound()
        
        _LOG.info("Setup completed successfully")
        return ucapi.SetupComplete()
        
    except Exception as e:
        _LOG.exception("Setup failed: %s", e)
        return ucapi.SetupError(error_type=ucapi.IntegrationSetupError.OTHER)


@api.listens_to(ucapi.Events.SETUP_DRIVER_USER_DATA)
async def on_setup_driver_user_data(msg: ucapi.SetupDriverUserData) -> ucapi.SetupAction:
    """Handle user data during setup.
    
    Args:
        msg: Setup user data message
        
    Returns:
        Setup action
    """
    return await on_setup_driver(msg)


async def main():
    """Main entry point."""
    global config_manager
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if os.getenv("UC_LOG_LEVEL") == "DEBUG" else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    
    _LOG.info("Starting Russound integration driver v%s", DRIVER_VERSION)
    
    # Initialize configuration
    config_dir = os.getenv("UC_CONFIG_HOME", ".")
    config_manager = RussoundConfig(config_dir)
    
    # Initialize integration API
    driver_path = os.path.join(os.path.dirname(__file__), "..")
    await api.init(driver_path, on_setup_driver)
    
    _LOG.info("Integration driver initialized")


if __name__ == "__main__":
    asyncio.run(main())
