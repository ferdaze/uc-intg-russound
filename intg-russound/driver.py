"""
Russound RIO integration driver for the Unfolded Circle Remote.

Entry point for the PyInstaller bundle that runs natively on the Remote.

:copyright: (c) 2026 by Jeff Ferdinandsen.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
import os

from const import DEFAULT_PORT, DeviceConfig
from device import RussoundDevice
from discover import RussoundDiscovery
from media_player import create_zone_entities
from setup import RussoundSetupFlow
from ucapi_framework import BaseConfigManager, BaseIntegrationDriver, get_config_path

_LOG = logging.getLogger("driver")


async def main() -> None:
    """Start the integration driver and run until the Remote stops it."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    level = os.getenv("UC_LOG_LEVEL", "INFO").upper()
    for logger_name in ("driver", "device", "media_player", "setup", "discover"):
        logging.getLogger(logger_name).setLevel(level)
    # aiorussound is chatty at DEBUG; keep it one notch quieter unless asked.
    logging.getLogger("aiorussound").setLevel(
        level if level != "DEBUG" else os.getenv("UC_RIO_LOG_LEVEL", "INFO").upper()
    )

    driver = BaseIntegrationDriver(
        device_class=RussoundDevice,
        # Zones are only known once the controller answers, so entities are
        # produced by a factory rather than a fixed class list.
        entity_classes=[create_zone_entities],
        require_connection_before_registry=True,
        driver_id="russound",
    )

    driver.config_manager = BaseConfigManager(
        get_config_path(driver.api.config_dir_path),
        driver.on_device_added,
        driver.on_device_removed,
        config_class=DeviceConfig,
    )

    await driver.register_all_configured_devices()

    discovery = RussoundDiscovery(port=DEFAULT_PORT, timeout=30)
    setup_handler = RussoundSetupFlow.create_handler(driver, discovery=discovery)

    await driver.api.init("driver.json", setup_handler)

    _LOG.info("Russound RIO integration driver started")
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
