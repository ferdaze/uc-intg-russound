"""Russound device handler."""
import asyncio
import logging
from typing import Callable, Optional

from aiorussound import RussoundClient, RussoundTcpConnectionHandler

_LOG = logging.getLogger(__name__)


class RussoundDevice:
    """Russound device manager."""

    def __init__(
        self,
        host: str,
        port: int = 9621,
        controller_id: int = 1,
        on_update: Optional[Callable] = None,
        on_connection_change: Optional[Callable] = None,
    ):
        """Initialize device."""
        self._host = host
        self._port = port
        self._controller_id = controller_id
        self._on_update = on_update
        self._on_connection_change = on_connection_change
        
        self._client: Optional[RussoundClient] = None
        self._connection: Optional[RussoundTcpConnectionHandler] = None
        self._connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._zones_cache = {}
        self._sources_cache = []

    async def connect(self) -> bool:
        """Connect to device."""
        try:
            _LOG.info(f"Connecting to {self._host}:{self._port}")
            
            self._connection = RussoundTcpConnectionHandler(
                host=self._host,
                port=self._port
            )
            
            self._client = RussoundClient(self._connection)
            
            # Register callback
            self._client.register_state_callback(self._state_callback)
            
            # Connect
            await self._client.connect()
            
            self._connected = True
            _LOG.info("Connected successfully")
            
            if self._on_connection_change:
                await self._on_connection_change(True)
            
            # Cache zone and source info
            await self._cache_device_info()
            
            return True
            
        except Exception as e:
            _LOG.error(f"Connection failed: {e}")
            self._connected = False
            if self._on_connection_change:
                await self._on_connection_change(False)
            return False

    async def disconnect(self) -> None:
        """Disconnect from device."""
        _LOG.info("Disconnecting")
        
        self._connected = False
        
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                _LOG.warning(f"Disconnect error: {e}")
            self._client = None
        
        self._connection = None
        
        if self._on_connection_change:
            await self._on_connection_change(False)

    def _state_callback(self, zone_obj) -> None:
        """Handle zone state updates."""
        if not self._on_update:
            return
        
        try:
            # Extract zone data
            zone_data = {
                "zone_id": zone_obj.zone_id,
                "power": zone_obj.power,
                "volume": getattr(zone_obj, "volume", 0),
                "mute": getattr(zone_obj, "mute", False),
                "source_name": getattr(zone_obj, "source_name", ""),
                "media_title": getattr(zone_obj, "media_title", ""),
                "media_artist": getattr(zone_obj, "media_artist", ""),
                "media_album": getattr(zone_obj, "media_album", ""),
            }
            
            asyncio.create_task(self._on_update(zone_data))
            
        except Exception as e:
            _LOG.error(f"State callback error: {e}")

    async def _cache_device_info(self) -> None:
        """Cache zone and source information."""
        if not self._client or not self._client.controllers:
            return
        
        controller = self._client.controllers.get(self._controller_id)
        if not controller:
            return
        
        # Cache sources
        if hasattr(controller, "sources"):
            for source_id, source in controller.sources.items():
                self._sources_cache.append({
                    "id": source_id,
                    "name": getattr(source, "name", f"Source {source_id}")
                })

    async def start_reconnect(self) -> None:
        """Start reconnection task."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Reconnection loop."""
        delay = 5
        max_delay = 60
        
        while not self._connected:
            try:
                await asyncio.sleep(delay)
                _LOG.info(f"Reconnecting (delay: {delay}s)")
                
                if await self.connect():
                    _LOG.info("Reconnected")
                    break
                
                delay = min(delay * 2, max_delay)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOG.error(f"Reconnect error: {e}")

    @property
    def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected and self._client and self._client.is_connected

    async def get_zone_state(self, zone_id: int) -> Optional[dict]:
        """Get zone state."""
        if not self._client or not self._client.controllers:
            return None
        
        controller = self._client.controllers.get(self._controller_id)
        if not controller or not hasattr(controller, "zones"):
            return None
        
        zone = controller.zones.get(zone_id)
        if not zone:
            return None
        
        return {
            "zone_id": zone_id,
            "power": zone.power,
            "volume": getattr(zone, "volume", 0),
            "mute": getattr(zone, "mute", False),
            "source_name": getattr(zone, "source_name", ""),
            "media_title": getattr(zone, "media_title", ""),
            "media_artist": getattr(zone, "media_artist", ""),
            "media_album": getattr(zone, "media_album", ""),
        }

    async def get_zone_info(self, zone_id: int) -> Optional[dict]:
        """Get zone information."""
        if not self._client or not self._client.controllers:
            return None
        
        controller = self._client.controllers.get(self._controller_id)
        if not controller or not hasattr(controller, "zones"):
            return None
        
        zone = controller.zones.get(zone_id)
        if not zone:
            return None
        
        return {
            "name": getattr(zone, "name", f"Zone {zone_id}"),
            "zone_id": zone_id,
        }

    def get_sources(self) -> list:
        """Get source list."""
        return self._sources_cache

    def get_source_id_by_name(self, name: str) -> Optional[int]:
        """Get source ID by name."""
        for source in self._sources_cache:
            if source["name"] == name:
                return source["id"]
        return None

    async def zone_on(self, zone_id: int) -> bool:
        """Turn zone on."""
        zone = await self._get_zone(zone_id)
        if not zone:
            return False
        
        try:
            await zone.set_power(True)
            return True
        except Exception as e:
            _LOG.error(f"Zone on failed: {e}")
            return False

    async def zone_off(self, zone_id: int) -> bool:
        """Turn zone off."""
        zone = await self._get_zone(zone_id)
        if not zone:
            return False
        
        try:
            await zone.set_power(False)
            return True
        except Exception as e:
            _LOG.error(f"Zone off failed: {e}")
            return False

    async def set_volume(self, zone_id: int, volume: int) -> bool:
        """Set volume (0-50)."""
        zone = await self._get_zone(zone_id)
        if not zone:
            return False
        
        try:
            await zone.set_volume(volume)
            return True
        except Exception as e:
            _LOG.error(f"Set volume failed: {e}")
            return False

    async def volume_up(self, zone_id: int) -> bool:
        """Volume up."""
        zone = await self._get_zone(zone_id)
        if not zone:
            return False
        
        try:
            current = getattr(zone, "volume", 0)
            await zone.set_volume(min(current + 1, 50))
            return True
        except Exception as e:
            _LOG.error(f"Volume up failed: {e}")
            return False

    async def volume_down(self, zone_id: int) -> bool:
        """Volume down."""
        zone = await self._get_zone(zone_id)
        if not zone:
            return False
        
        try:
            current = getattr(zone, "volume", 0)
            await zone.set_volume(max(current - 1, 0))
            return True
        except Exception as e:
            _LOG.error(f"Volume down failed: {e}")
            return False

    async def mute_toggle(self, zone_id: int) -> bool:
        """Toggle mute."""
        zone = await self._get_zone(zone_id)
        if not zone:
            return False
        
        try:
            current_mute = getattr(zone, "mute", False)
            await zone.set_mute(not current_mute)
            return True
        except Exception as e:
            _LOG.error(f"Mute toggle failed: {e}")
            return False

    async def select_source(self, zone_id: int, source_id: int) -> bool:
        """Select source."""
        zone = await self._get_zone(zone_id)
        if not zone:
            return False
        
        try:
            await zone.set_source(source_id)
            return True
        except Exception as e:
            _LOG.error(f"Select source failed: {e}")
            return False

    async def _get_zone(self, zone_id: int):
        """Get zone object."""
        if not self._client or not self._client.controllers:
            return None
        
        controller = self._client.controllers.get(self._controller_id)
        if not controller or not hasattr(controller, "zones"):
            return None
        
        return controller.zones.get(zone_id)
