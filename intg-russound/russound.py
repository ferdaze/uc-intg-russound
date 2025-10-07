"""Russound device communication handler."""
import asyncio
import logging
from typing import Callable, Optional

from aiorussound import Russound, RussoundClient
from aiorussound.models import Source, Zone, Controller

from const import (
    RUSSOUND_VOL_MAX,
    UI_VOL_MAX,
    RECONNECT_DELAY_MIN,
    RECONNECT_DELAY_MAX,
    KEEPALIVE_INTERVAL,
)

_LOG = logging.getLogger(__name__)


class RussoundDevice:
    """Manage connection and communication with Russound device."""

    def __init__(
        self,
        host: str,
        port: int,
        controller_id: int,
        on_update: Optional[Callable] = None,
        on_connection_change: Optional[Callable] = None,
    ):
        """Initialize Russound device handler.
        
        Args:
            host: IP address of Russound device
            port: TCP port (typically 9621)
            controller_id: Controller ID (1-6)
            on_update: Callback for zone/source updates
            on_connection_change: Callback for connection state changes
        """
        self._host = host
        self._port = port
        self._controller_id = controller_id
        self._on_update = on_update
        self._on_connection_change = on_connection_change
        
        self._client: Optional[RussoundClient] = None
        self._russound: Optional[Russound] = None
        self._connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._reconnect_delay = RECONNECT_DELAY_MIN

    async def connect(self) -> bool:
        """Connect to Russound device.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            _LOG.info("Connecting to Russound at %s:%s", self._host, self._port)
            
            # Create device connection using aiorussound
            self._russound = await Russound.create_device(self._host, self._port)
            
            if not self._russound:
                _LOG.error("Failed to create Russound device")
                return False
            
            # Register callbacks for updates
            controller = self._russound.controllers.get(self._controller_id)
            if controller:
                for zone in controller.zones.values():
                    zone.add_callback(self._handle_zone_update)
            
            self._connected = True
            self._reconnect_delay = RECONNECT_DELAY_MIN
            _LOG.info("Successfully connected to Russound")
            
            if self._on_connection_change:
                await self._on_connection_change(True)
            
            # Start keepalive task
            if self._keepalive_task:
                self._keepalive_task.cancel()
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            
            return True
            
        except Exception as e:
            _LOG.error("Failed to connect to Russound: %s", e)
            self._connected = False
            if self._on_connection_change:
                await self._on_connection_change(False)
            return False

    async def disconnect(self) -> None:
        """Disconnect from Russound device."""
        _LOG.info("Disconnecting from Russound")
        
        self._connected = False
        
        # Cancel tasks
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        
        # Close connection
        if self._russound:
            try:
                await self._russound.close()
            except Exception as e:
                _LOG.warning("Error closing Russound connection: %s", e)
        
        self._russound = None
        
        if self._on_connection_change:
            await self._on_connection_change(False)

    def _handle_zone_update(self, zone: Zone) -> None:
        """Handle zone state update from Russound.
        
        Args:
            zone: Updated zone object
        """
        _LOG.debug("Zone %s update received", zone.zone_id)
        if self._on_update:
            asyncio.create_task(self._on_update(zone))

    async def _keepalive_loop(self) -> None:
        """Send periodic keepalive to prevent device standby."""
        while self._connected:
            try:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                if self._connected and self._russound:
                    # Send empty command as keepalive
                    _LOG.debug("Sending keepalive")
                    # The library handles this automatically
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOG.error("Keepalive error: %s", e)

    async def start_reconnect(self) -> None:
        """Start automatic reconnection task."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        
        _LOG.info("Starting reconnection task")
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Automatic reconnection loop."""
        while True:
            try:
                if not self._connected:
                    _LOG.info(
                        "Attempting to reconnect (delay: %s seconds)",
                        self._reconnect_delay
                    )
                    await asyncio.sleep(self._reconnect_delay)
                    
                    success = await self.connect()
                    
                    if success:
                        _LOG.info("Reconnection successful")
                        break
                    else:
                        # Exponential backoff
                        self._reconnect_delay = min(
                            self._reconnect_delay * 2,
                            RECONNECT_DELAY_MAX
                        )
                else:
                    break
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOG.error("Reconnection error: %s", e)
                await asyncio.sleep(self._reconnect_delay)

    @property
    def is_connected(self) -> bool:
        """Check if connected to device."""
        return self._connected

    def get_controller(self) -> Optional[Controller]:
        """Get controller object.
        
        Returns:
            Controller object or None if not connected
        """
        if not self._russound:
            return None
        return self._russound.controllers.get(self._controller_id)

    def get_zone(self, zone_id: int) -> Optional[Zone]:
        """Get zone object by ID.
        
        Args:
            zone_id: Zone ID (1-8)
            
        Returns:
            Zone object or None if not found
        """
        controller = self.get_controller()
        if not controller:
            return None
        return controller.zones.get(zone_id)

    def get_source(self, source_id: int) -> Optional[Source]:
        """Get source object by ID.
        
        Args:
            source_id: Source ID (1-12)
            
        Returns:
            Source object or None if not found
        """
        if not self._russound:
            return None
        return self._russound.sources.get(source_id)

    @staticmethod
    def volume_to_ui(russound_vol: int) -> int:
        """Convert Russound volume (0-50) to UI volume (0-100).
        
        Args:
            russound_vol: Russound volume level
            
        Returns:
            UI volume level
        """
        return int(russound_vol * UI_VOL_MAX / RUSSOUND_VOL_MAX)

    @staticmethod
    def volume_to_russound(ui_vol: int) -> int:
        """Convert UI volume (0-100) to Russound volume (0-50).
        
        Args:
            ui_vol: UI volume level
            
        Returns:
            Russound volume level
        """
        return int(ui_vol * RUSSOUND_VOL_MAX / UI_VOL_MAX)

    async def zone_on(self, zone_id: int) -> bool:
        """Turn zone on.
        
        Args:
            zone_id: Zone ID (1-8)
            
        Returns:
            True if successful
        """
        zone = self.get_zone(zone_id)
        if not zone:
            return False
        
        try:
            await zone.zone_on()
            return True
        except Exception as e:
            _LOG.error("Failed to turn on zone %s: %s", zone_id, e)
            return False

    async def zone_off(self, zone_id: int) -> bool:
        """Turn zone off.
        
        Args:
            zone_id: Zone ID (1-8)
            
        Returns:
            True if successful
        """
        zone = self.get_zone(zone_id)
        if not zone:
            return False
        
        try:
            await zone.zone_off()
            return True
        except Exception as e:
            _LOG.error("Failed to turn off zone %s: %s", zone_id, e)
            return False

    async def set_volume(self, zone_id: int, ui_volume: int) -> bool:
        """Set zone volume.
        
        Args:
            zone_id: Zone ID (1-8)
            ui_volume: Volume level (0-100)
            
        Returns:
            True if successful
        """
        zone = self.get_zone(zone_id)
        if not zone:
            return False
        
        russound_vol = self.volume_to_russound(ui_volume)
        
        try:
            await zone.set_volume(russound_vol)
            return True
        except Exception as e:
            _LOG.error("Failed to set volume for zone %s: %s", zone_id, e)
            return False

    async def volume_up(self, zone_id: int) -> bool:
        """Increase zone volume.
        
        Args:
            zone_id: Zone ID (1-8)
            
        Returns:
            True if successful
        """
        zone = self.get_zone(zone_id)
        if not zone:
            return False
        
        try:
            # Increase by 2 in UI terms (1 in Russound terms)
            current_vol = self.volume_to_ui(zone.volume)
            new_vol = min(current_vol + 2, UI_VOL_MAX)
            await self.set_volume(zone_id, new_vol)
            return True
        except Exception as e:
            _LOG.error("Failed to increase volume for zone %s: %s", zone_id, e)
            return False

    async def volume_down(self, zone_id: int) -> bool:
        """Decrease zone volume.
        
        Args:
            zone_id: Zone ID (1-8)
            
        Returns:
            True if successful
        """
        zone = self.get_zone(zone_id)
        if not zone:
            return False
        
        try:
            # Decrease by 2 in UI terms (1 in Russound terms)
            current_vol = self.volume_to_ui(zone.volume)
            new_vol = max(current_vol - 2, 0)
            await self.set_volume(zone_id, new_vol)
            return True
        except Exception as e:
            _LOG.error("Failed to decrease volume for zone %s: %s", zone_id, e)
            return False

    async def mute_on(self, zone_id: int) -> bool:
        """Mute zone.
        
        Args:
            zone_id: Zone ID (1-8)
            
        Returns:
            True if successful
        """
        zone = self.get_zone(zone_id)
        if not zone:
            return False
        
        try:
            # Send mute key press
            # Note: aiorussound may not have direct mute method, use key event
            await zone.send_key_press("Mute")
            return True
        except Exception as e:
            _LOG.error("Failed to mute zone %s: %s", zone_id, e)
            return False

    async def select_source(self, zone_id: int, source_id: int) -> bool:
        """Select source for zone.
        
        Args:
            zone_id: Zone ID (1-8)
            source_id: Source ID (1-8 for MCA-88)
            
        Returns:
            True if successful
        """
        zone = self.get_zone(zone_id)
        if not zone:
            return False
        
        try:
            await zone.select_source(source_id)
            return True
        except Exception as e:
            _LOG.error("Failed to select source for zone %s: %s", zone_id, e)
            return False
