"""
Russound integration for Unfolded Circle Remote R3.
Supports Russound MCA-88 and other RIO-compatible devices.
"""

import asyncio
import logging
from typing import Any

from aiorussound import RussoundClient, RussoundTcpConnectionHandler
from ucapi import EntityTypes, MediaPlayer, StatusCodes
from ucapi.media_player import (
    Attributes,
    Commands,
    Features,
    States,
)

_LOG = logging.getLogger(__name__)

# Constants
DEFAULT_PORT = 9621
VOLUME_STEP = 2
MIN_VOLUME = 0
MAX_VOLUME = 50


class RussoundDevice:
    """Represents a Russound controller device."""

    def __init__(self, host: str, port: int = DEFAULT_PORT):
        """Initialize the Russound device."""
        self.host = host
        self.port = port
        self._connection_handler = None
        self._client = None
        self._zones = {}
        self._available = False
        self._reconnect_task = None
        
    async def connect(self) -> bool:
        """Connect to the Russound device."""
        try:
            # Create connection handler
            self._connection_handler = RussoundTcpConnectionHandler(
                host=self.host,
                port=self.port
            )
            
            # Create client
            self._client = RussoundClient(self._connection_handler)
            
            # Register state callback
            self._client.register_state_callback(self._on_zone_state_change)
            
            # Connect to device
            await self._client.connect()
            
            _LOG.info(f"Connected to Russound device at {self.host}:{self.port}")
            
            # Discover zones
            await self._discover_zones()
            
            self._available = True
            return True
            
        except Exception as e:
            _LOG.error(f"Failed to connect to Russound device: {e}")
            self._available = False
            return False
    
    async def disconnect(self):
        """Disconnect from the Russound device."""
        if self._reconnect_task:
            self._reconnect_task.cancel()
            
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                _LOG.error(f"Error disconnecting: {e}")
            finally:
                self._client = None
                self._connection_handler = None
                self._available = False
    
    async def _discover_zones(self):
        """Discover all zones from all controllers."""
        if not self._client or not self._client.controllers:
            _LOG.warning("No controllers found")
            return
        
        self._zones.clear()
        
        # Iterate through all controllers
        for controller_id, controller in self._client.controllers.items():
            _LOG.info(f"Found controller {controller_id}: {controller.type}")
            
            # Iterate through all zones in this controller
            for zone_id, zone in controller.zones.items():
                zone_key = f"C{controller_id}Z{zone_id}"
                self._zones[zone_key] = RussoundZone(
                    zone=zone,
                    controller_id=controller_id,
                    zone_id=zone_id,
                    device=self
                )
                _LOG.info(f"Discovered zone: {zone_key} - {zone.name}")
    
    def _on_zone_state_change(self, zone):
        """Handle zone state changes."""
        # Find the corresponding RussoundZone wrapper
        for zone_key, russound_zone in self._zones.items():
            if russound_zone._zone == zone:
                russound_zone.update_attributes()
                break
    
    def get_zones(self):
        """Get all discovered zones."""
        return self._zones
    
    @property
    def is_available(self) -> bool:
        """Check if device is available."""
        return self._available and self._client and self._client.is_connected


class RussoundZone:
    """Represents a Russound zone (media player entity)."""

    def __init__(self, zone, controller_id: int, zone_id: int, device: RussoundDevice):
        """Initialize the Russound zone."""
        self._zone = zone
        self._controller_id = controller_id
        self._zone_id = zone_id
        self._device = device
        self._entity = None
        
    def create_entity(self) -> MediaPlayer:
        """Create a media player entity for this zone."""
        zone_key = f"C{self._controller_id}Z{self._zone_id}"
        
        # Define supported features
        features = [
            Features.ON_OFF,
            Features.VOLUME,
            Features.VOLUME_UP_DOWN,
            Features.MUTE_TOGGLE,
            Features.MUTE,
            Features.UNMUTE,
            Features.SELECT_SOURCE,
        ]
        
        # Define supported attributes
        attributes = {
            Attributes.STATE: States.OFF,
            Attributes.VOLUME: 0,
            Attributes.MUTED: False,
            Attributes.SOURCE: "",
            Attributes.SOURCE_LIST: self._get_source_list(),
        }
        
        # Create entity
        self._entity = MediaPlayer(
            identifier=zone_key,
            name=self._zone.name or f"Zone {self._zone_id}",
            features=features,
            attributes=attributes,
        )
        
        # Update initial attributes
        self.update_attributes()
        
        return self._entity
    
    def _get_source_list(self) -> list[str]:
        """Get list of available sources."""
        source_list = []
        
        if self._device._client and self._device._client.controllers:
            controller = self._device._client.controllers.get(self._controller_id)
            if controller and hasattr(controller, 'sources'):
                for source_id, source in controller.sources.items():
                    source_name = getattr(source, 'name', f"Source {source_id}")
                    source_list.append(source_name)
        
        return source_list
    
    def update_attributes(self):
        """Update entity attributes from zone state."""
        if not self._entity:
            return
        
        try:
            # Update state
            if self._zone.power:
                self._entity.attributes[Attributes.STATE] = States.PLAYING
            else:
                self._entity.attributes[Attributes.STATE] = States.OFF
            
            # Update volume (convert 0-50 range to 0-100)
            volume = int((self._zone.volume / MAX_VOLUME) * 100)
            self._entity.attributes[Attributes.VOLUME] = volume
            
            # Update mute state
            self._entity.attributes[Attributes.MUTED] = self._zone.mute
            
            # Update current source
            if hasattr(self._zone, 'source_name'):
                self._entity.attributes[Attributes.SOURCE] = self._zone.source_name
            
            # Update media information if available
            if hasattr(self._zone, 'media_title') and self._zone.media_title:
                self._entity.attributes[Attributes.MEDIA_TITLE] = self._zone.media_title
            
            if hasattr(self._zone, 'media_artist') and self._zone.media_artist:
                self._entity.attributes[Attributes.MEDIA_ARTIST] = self._zone.media_artist
            
            if hasattr(self._zone, 'media_album') and self._zone.media_album:
                self._entity.attributes[Attributes.MEDIA_ALBUM] = self._zone.media_album
            
        except Exception as e:
            _LOG.error(f"Error updating zone attributes: {e}")
    
    async def handle_command(self, command: str, params: dict[str, Any] | None = None) -> StatusCodes:
        """Handle media player commands."""
        try:
            if command == Commands.ON:
                await self._zone.set_power(True)
                return StatusCodes.OK
                
            elif command == Commands.OFF:
                await self._zone.set_power(False)
                return StatusCodes.OK
                
            elif command == Commands.TOGGLE:
                await self._zone.set_power(not self._zone.power)
                return StatusCodes.OK
                
            elif command == Commands.VOLUME:
                if params and Attributes.VOLUME in params:
                    # Convert 0-100 range to 0-50
                    volume = int((params[Attributes.VOLUME] / 100) * MAX_VOLUME)
                    await self._zone.set_volume(volume)
                    return StatusCodes.OK
                    
            elif command == Commands.VOLUME_UP:
                current_volume = self._zone.volume
                new_volume = min(current_volume + VOLUME_STEP, MAX_VOLUME)
                await self._zone.set_volume(new_volume)
                return StatusCodes.OK
                
            elif command == Commands.VOLUME_DOWN:
                current_volume = self._zone.volume
                new_volume = max(current_volume - VOLUME_STEP, MIN_VOLUME)
                await self._zone.set_volume(new_volume)
                return StatusCodes.OK
                
            elif command == Commands.MUTE_TOGGLE:
                await self._zone.set_mute(not self._zone.mute)
                return StatusCodes.OK
                
            elif command == Commands.MUTE:
                await self._zone.set_mute(True)
                return StatusCodes.OK
                
            elif command == Commands.UNMUTE:
                await self._zone.set_mute(False)
                return StatusCodes.OK
                
            elif command == Commands.SELECT_SOURCE:
                if params and Attributes.SOURCE in params:
                    source_name = params[Attributes.SOURCE]
                    source_id = self._get_source_id_by_name(source_name)
                    if source_id:
                        await self._zone.set_source(source_id)
                        return StatusCodes.OK
                    else:
                        _LOG.error(f"Source not found: {source_name}")
                        return StatusCodes.BAD_REQUEST
            
            _LOG.warning(f"Unsupported command: {command}")
            return StatusCodes.BAD_REQUEST
            
        except Exception as e:
            _LOG.error(f"Error handling command {command}: {e}")
            return StatusCodes.SERVER_ERROR
    
    def _get_source_id_by_name(self, source_name: str) -> int | None:
        """Get source ID by name."""
        if self._device._client and self._device._client.controllers:
            controller = self._device._client.controllers.get(self._controller_id)
            if controller and hasattr(controller, 'sources'):
                for source_id, source in controller.sources.items():
                    if getattr(source, 'name', '') == source_name:
                        return source_id
        return None


# Integration setup function
async def setup_russound_integration(api, config: dict[str, Any]):
    """
    Set up the Russound integration.
    
    Args:
        api: Unfolded Circle API instance
        config: Configuration dict with 'host' and optional 'port'
    """
    host = config.get("host")
    port = config.get("port", DEFAULT_PORT)
    
    if not host:
        _LOG.error("Russound host not configured")
        return False
    
    # Create device
    device = RussoundDevice(host, port)
    
    # Connect to device
    if not await device.connect():
        _LOG.error("Failed to connect to Russound device")
        return False
    
    # Register all zones as media player entities
    zones = device.get_zones()
    for zone_key, zone in zones.items():
        entity = zone.create_entity()
        
        # Register command handler
        async def command_handler(
            entity_id: str,
            command: str,
            params: dict[str, Any] | None = None
        ) -> StatusCodes:
            # Find the zone
            for zk, z in zones.items():
                if z._entity and z._entity.id == entity_id:
                    return await z.handle_command(command, params)
            return StatusCodes.NOT_FOUND
        
        # Register entity with API
        api.available_entities.add(entity)
        
    _LOG.info(f"Russound integration setup complete. Registered {len(zones)} zones.")
    return True
