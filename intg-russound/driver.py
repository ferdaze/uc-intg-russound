#!/usr/bin/env python3
"""Russound RIO Integration Driver for Unfolded Circle Remote."""
import asyncio
import logging
import sys
from typing import Any

import ucapi
from ucapi import media_player

from . import const
from .config import RussoundConfig
from .russound import RussoundController

_LOG = logging.getLogger(__name__)


class RussoundDriver:
    """Russound Integration Driver."""

    def __init__(self):
        """Initialize the driver."""
        self.api = ucapi.IntegrationAPI(const.DRIVER_ID)
        self.config = RussoundConfig()
        self.controller = None
        self.entities = {}
        
        # Register callbacks
        self.api.set_setup_handler(self.handle_setup)
        self.api.on(ucapi.Events.CONNECT, self.handle_connect)
        self.api.on(ucapi.Events.DISCONNECT, self.handle_disconnect)
        self.api.on(ucapi.Events.ENTER_STANDBY, self.handle_standby)
        self.api.on(ucapi.Events.EXIT_STANDBY, self.handle_exit_standby)

    async def handle_setup(self, msg):
        """Handle driver setup."""
        _LOG.info("Setup driver with data: %s", msg.setup_data)
        
        # Get setup data
        host = msg.setup_data.get("host", "")
        port = msg.setup_data.get("port", const.DEFAULT_PORT)
        name = msg.setup_data.get("name", const.DEFAULT_NAME)
        
        if not host:
            _LOG.error("No host provided")
            return ucapi.SetupError(error_type=ucapi.IntegrationSetupError.OTHER)
        
        # Test connection
        test_controller = RussoundController(host, port)
        if not await test_controller.connect():
            await test_controller.disconnect()
            return ucapi.SetupError(error_type=ucapi.IntegrationSetupError.CONNECTION_REFUSED)
        
        # Save configuration
        config = {
            "host": host,
            "port": port,
            "name": name,
        }
        self.config.save(config)
        
        # Create controller
        self.controller = test_controller
        self.controller.register_callback(self.handle_zone_update)
        
        # Create entities for each zone
        await self._create_entities()
        
        await test_controller.disconnect()
        
        return ucapi.SetupComplete()

    async def _create_entities(self):
        """Create media player entities for each zone."""
        if not self.controller:
            return
        
        for zone_id, zone_data in self.controller.zones.items():
            entity_id = f"zone_{zone_id}"
            
            # Get source list
            source_list = [
                self.controller.get_source_name(src_id)
                for src_id in self.controller.sources.keys()
            ]
            
            # Create media player entity
            entity = media_player.MediaPlayer(
                identifier=entity_id,
                name=ucapi.EntityName(zone_data["name"], "en"),
                features=[
                    media_player.Features.ON_OFF,
                    media_player.Features.VOLUME,
                    media_player.Features.VOLUME_UP_DOWN,
                    media_player.Features.MUTE_TOGGLE,
                    media_player.Features.SELECT_SOURCE,
                ],
                attributes={
                    media_player.Attributes.STATE: self._get_zone_state(zone_id),
                    media_player.Attributes.VOLUME: zone_data.get("volume", 0),
                    media_player.Attributes.MUTED: zone_data.get("mute", False),
                    media_player.Attributes.SOURCE: self.controller.get_source_name(
                        zone_data.get("source", 1)
                    ),
                    media_player.Attributes.SOURCE_LIST: source_list,
                },
                command_handler=self.handle_command,
            )
            
            self.entities[entity_id] = entity
            self.api.available_entities.append(entity)
            _LOG.info("Created entity: %s", entity_id)

    def _get_zone_state(self, zone_id):
        """Get zone state."""
        if not self.controller or zone_id not in self.controller.zones:
            return media_player.States.OFF
        
        zone = self.controller.zones[zone_id]
        if zone.get("power"):
            return media_player.States.ON
        return media_player.States.OFF

    async def handle_connect(self):
        """Handle remote connection."""
        _LOG.info("Remote connected")
        
        # Load configuration
        config = self.config.load()
        if not config:
            _LOG.error("No configuration found")
            return
        
        # Connect to controller
        host = config.get("host")
        port = config.get("port", const.DEFAULT_PORT)
        
        if not host:
            _LOG.error("No host in configuration")
            return
        
        self.controller = RussoundController(host, port)
        self.controller.register_callback(self.handle_zone_update)
        
        if await self.controller.connect():
            _LOG.info("Connected to Russound controller")
            # Update entities with current state
            await self._update_all_entities()
        else:
            _LOG.error("Failed to connect to Russound controller")

    async def handle_disconnect(self):
        """Handle remote disconnection."""
        _LOG.info("Remote disconnected")
        if self.controller:
            await self.controller.disconnect()

    async def handle_standby(self):
        """Handle remote entering standby."""
        _LOG.info("Remote entering standby")

    async def handle_exit_standby(self):
        """Handle remote exiting standby."""
        _LOG.info("Remote exiting standby")
        if self.controller:
            await self._update_all_entities()

    async def handle_command(self, entity, cmd_id, params=None):
        """Handle media player commands."""
        if not self.controller:
            return ucapi.StatusCodes.SERVER_ERROR
        
        # Extract zone ID from entity identifier
        zone_id = int(entity.identifier.split("_")[1])
        
        _LOG.info("Command %s for zone %s with params %s", cmd_id, zone_id, params)
        
        try:
            if cmd_id == media_player.Commands.ON:
                await self.controller.zone_on(zone_id)
            elif cmd_id == media_player.Commands.OFF:
                await self.controller.zone_off(zone_id)
            elif cmd_id == media_player.Commands.TOGGLE:
                zone_state = self.controller.get_zone_state(zone_id)
                if zone_state and zone_state.get("power"):
                    await self.controller.zone_off(zone_id)
                else:
                    await self.controller.zone_on(zone_id)
            elif cmd_id == media_player.Commands.VOLUME:
                if params and "volume" in params:
                    # Convert from 0-100 to 0-50
                    volume = int(params["volume"] * const.MAX_VOLUME / 100)
                    await self.controller.set_volume(zone_id, volume)
            elif cmd_id == media_player.Commands.VOLUME_UP:
                await self.controller.volume_up(zone_id)
            elif cmd_id == media_player.Commands.VOLUME_DOWN:
                await self.controller.volume_down(zone_id)
            elif cmd_id == media_player.Commands.MUTE_TOGGLE:
                await self.controller.mute_toggle(zone_id)
            elif cmd_id == media_player.Commands.SELECT_SOURCE:
                if params and "source" in params:
                    source_name = params["source"]
                    # Find source ID by name
                    for src_id, src_data in self.controller.sources.items():
                        if src_data["name"] == source_name:
                            await self.controller.select_source(zone_id, src_id)
                            break
            else:
                _LOG.warning("Unsupported command: %s", cmd_id)
                return ucapi.StatusCodes.NOT_IMPLEMENTED
            
            # Update entity state
            await self._update_entity(entity.identifier)
            return ucapi.StatusCodes.OK
            
        except Exception as ex:
            _LOG.error("Error executing command %s: %s", cmd_id, ex)
            return ucapi.StatusCodes.SERVER_ERROR

    def handle_zone_update(self, zone_id, updates):
        """Handle zone state updates from controller."""
        entity_id = f"zone_{zone_id}"
        asyncio.create_task(self._update_entity(entity_id))

    async def _update_entity(self, entity_id):
        """Update entity state."""
        if entity_id not in self.entities or not self.controller:
            return
        
        entity = self.entities[entity_id]
        zone_id = int(entity_id.split("_")[1])
        zone_state = self.controller.get_zone_state(zone_id)
        
        if not zone_state:
            return
        
        # Update attributes
        attributes = {
            media_player.Attributes.STATE: self._get_zone_state(zone_id),
            media_player.Attributes.VOLUME: zone_state.get("volume", 0),
            media_player.Attributes.MUTED: zone_state.get("mute", False),
            media_player.Attributes.SOURCE: self.controller.get_source_name(
                zone_state.get("source", 1)
            ),
        }
        
        self.api.configured_entities.update_attributes(entity_id, attributes)

    async def _update_all_entities(self):
        """Update all entity states."""
        for entity_id in self.entities.keys():
            await self._update_entity(entity_id)

def run(self):
        """Run the integration driver."""
        _LOG.info("Starting Russound Integration Driver v%s", const.DRIVER_VERSION)
        
        # Find driver.json - it should be in the parent directory of the binary
        import os
        driver_path = os.path.dirname(os.path.abspath(__file__))
        
        # When running as PyInstaller bundle, look in parent directory
        if getattr(sys, 'frozen', False):
            # Running as compiled binary
            driver_path = os.path.dirname(sys.executable)
            driver_json = os.path.join(os.path.dirname(driver_path), "driver.json")
        else:
            # Running as script
            driver_json = os.path.join(os.path.dirname(driver_path), "driver.json")
        
        _LOG.info("Looking for driver.json at: %s", driver_json)
        
        if not os.path.exists(driver_json):
            _LOG.error("driver.json not found at %s", driver_json)
            sys.exit(1)
        
        try:
            self.api.init(driver_json)
            self.api.loop.run_forever()
        except KeyboardInterrupt:
            _LOG.info("Shutting down...")
        except Exception as e:
            _LOG.error("Fatal error: %s", e, exc_info=True)
            sys.exit(1)
        finally:
            if self.controller:
                asyncio.run(self.controller.disconnect())

def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    try:
        driver = RussoundDriver()
        driver.run()
    except Exception as e:
        _LOG.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
