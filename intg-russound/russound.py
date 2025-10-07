"""Russound RIO protocol handler."""
import asyncio
import logging
from typing import Any, Callable

import aiorussound

# Use absolute import
import const

from .const import (
    MAX_SOURCES,
    MAX_ZONES,
    MAX_VOLUME,
    MIN_VOLUME,
    STATE_OFF,
    STATE_ON,
    STATE_PLAYING,
)

_LOG = logging.getLogger(__name__)


class RussoundController:
    """Russound RIO controller interface."""

    def __init__(self, host, port=9621):
        """Initialize Russound controller."""
        self.host = host
        self.port = port
        self.client = None
        self.zones = {}
        self.sources = {}
        self.callbacks = []
        self._connection_task = None

    async def connect(self):
        """Connect to Russound controller."""
        try:
            _LOG.info("Connecting to Russound at %s:%s", self.host, self.port)
            self.client = aiorussound.RussoundClient(self.host, self.port)
            
            # Set up callbacks
            self.client.register_state_update_callback(self._handle_state_update)
            
            await self.client.connect()
            _LOG.info("Successfully connected to Russound controller")
            
            # Discover zones and sources
            await self._discover()
            
            return True
        except Exception as ex:
            _LOG.error("Failed to connect to Russound: %s", ex)
            return False

    async def disconnect(self):
        """Disconnect from Russound controller."""
        if self.client:
            try:
                await self.client.disconnect()
                _LOG.info("Disconnected from Russound controller")
            except Exception as ex:
                _LOG.error("Error disconnecting: %s", ex)
            finally:
                self.client = None

    async def _discover(self):
        """Discover zones and sources."""
        if not self.client:
            return

        try:
            # Get controller info
            controllers = await self.client.enumerate_controllers()
            
            if not controllers:
                _LOG.warning("No controllers found")
                return
            
            # Get zones
            for controller_id in controllers:
                zones = await self.client.enumerate_zones(controller_id)
                for zone_id in zones:
                    zone = self.client.get_zone(controller_id, zone_id)
                    if zone:
                        self.zones[zone_id] = {
                            "id": zone_id,
                            "controller_id": controller_id,
                            "name": zone.name or f"Zone {zone_id}",
                            "power": zone.power,
                            "volume": zone.volume,
                            "source": zone.source,
                            "bass": zone.bass,
                            "treble": zone.treble,
                            "balance": zone.balance,
                            "mute": zone.mute,
                            "loudness": zone.loudness,
                        }
                        _LOG.info("Discovered zone %s: %s", zone_id, zone.name)
            
            # Get sources
            for controller_id in controllers:
                sources = await self.client.enumerate_sources(controller_id)
                for source_id in sources:
                    source = self.client.get_source(controller_id, source_id)
                    if source:
                        self.sources[source_id] = {
                            "id": source_id,
                            "name": source.name or f"Source {source_id}",
                        }
                        _LOG.info("Discovered source %s: %s", source_id, source.name)
                        
        except Exception as ex:
            _LOG.error("Error discovering devices: %s", ex)

    def _handle_state_update(self, controller_id, zone_id, updates):
        """Handle state updates from controller."""
        if zone_id in self.zones:
            self.zones[zone_id].update(updates)
            _LOG.debug("Zone %s updated: %s", zone_id, updates)
            
            # Notify callbacks
            for callback in self.callbacks:
                try:
                    callback(zone_id, updates)
                except Exception as ex:
                    _LOG.error("Error in state update callback: %s", ex)

    def register_callback(self, callback):
        """Register callback for state updates."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def unregister_callback(self, callback):
        """Unregister callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    async def zone_on(self, zone_id):
        """Turn zone on."""
        if not self.client or zone_id not in self.zones:
            return False
        
        try:
            zone_info = self.zones[zone_id]
            zone = self.client.get_zone(zone_info["controller_id"], zone_id)
            if zone:
                await zone.set_power(True)
                return True
        except Exception as ex:
            _LOG.error("Error turning zone %s on: %s", zone_id, ex)
        return False

    async def zone_off(self, zone_id):
        """Turn zone off."""
        if not self.client or zone_id not in self.zones:
            return False
        
        try:
            zone_info = self.zones[zone_id]
            zone = self.client.get_zone(zone_info["controller_id"], zone_id)
            if zone:
                await zone.set_power(False)
                return True
        except Exception as ex:
            _LOG.error("Error turning zone %s off: %s", zone_id, ex)
        return False

    async def set_volume(self, zone_id, volume):
        """Set zone volume (0-50)."""
        if not self.client or zone_id not in self.zones:
            return False
        
        try:
            # Clamp volume
            volume = max(MIN_VOLUME, min(MAX_VOLUME, volume))
            zone_info = self.zones[zone_id]
            zone = self.client.get_zone(zone_info["controller_id"], zone_id)
            if zone:
                await zone.set_volume(volume)
                return True
        except Exception as ex:
            _LOG.error("Error setting zone %s volume: %s", zone_id, ex)
        return False

    async def volume_up(self, zone_id):
        """Increase zone volume."""
        if zone_id not in self.zones:
            return False
        
        current_volume = self.zones[zone_id].get("volume", 0)
        return await self.set_volume(zone_id, current_volume + 2)

    async def volume_down(self, zone_id):
        """Decrease zone volume."""
        if zone_id not in self.zones:
            return False
        
        current_volume = self.zones[zone_id].get("volume", 0)
        return await self.set_volume(zone_id, current_volume - 2)

    async def mute_toggle(self, zone_id):
        """Toggle zone mute."""
        if not self.client or zone_id not in self.zones:
            return False
        
        try:
            zone_info = self.zones[zone_id]
            zone = self.client.get_zone(zone_info["controller_id"], zone_id)
            if zone:
                current_mute = self.zones[zone_id].get("mute", False)
                await zone.set_mute(not current_mute)
                return True
        except Exception as ex:
            _LOG.error("Error toggling zone %s mute: %s", zone_id, ex)
        return False

    async def select_source(self, zone_id, source_id):
        """Select source for zone."""
        if not self.client or zone_id not in self.zones:
            return False
        
        try:
            zone_info = self.zones[zone_id]
            zone = self.client.get_zone(zone_info["controller_id"], zone_id)
            if zone:
                await zone.set_source(source_id)
                return True
        except Exception as ex:
            _LOG.error("Error selecting source %s for zone %s: %s", source_id, zone_id, ex)
        return False

    def get_zone_state(self, zone_id):
        """Get current zone state."""
        return self.zones.get(zone_id)

    def get_source_name(self, source_id):
        """Get source name."""
        if source_id in self.sources:
            return self.sources[source_id]["name"]
        return f"Source {source_id}"
