"""
Russound Integration Driver for the Unfolded Circle Remote Two/3.

Entry point of the integration. Runs natively on the Remote (packaged with PyInstaller)
or on any host with Python 3.11+ for development.

:copyright: (c) 2026 by ferdaze.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
import os

from const import DeviceConfig
from device import RussoundDevice
from media_player import RussoundZoneMediaPlayer
from setup import RussoundSetupFlow
from ucapi_framework import BaseConfigManager, BaseIntegrationDriver, get_config_path

_LOG = logging.getLogger("driver")

_INTEGRATION_LOGGERS = ("driver", "device", "media_player", "setup", "rio", "russound")


def create_zone_entities(config: DeviceConfig, device: RussoundDevice) -> list[RussoundZoneMediaPlayer]:
    """Create one media player entity per configured zone."""
    return [RussoundZoneMediaPlayer(config, device, zone) for zone in config.zones]


async def main():
    """Start the Russound integration driver."""
    logging.basicConfig(format="%(asctime)s %(levelname)-8s %(name)-12s %(message)s")

    level = os.getenv("UC_LOG_LEVEL", "INFO").upper()
    for name in _INTEGRATION_LOGGERS:
        logging.getLogger(name).setLevel(level)

    driver = BaseIntegrationDriver(
        device_class=RussoundDevice,
        entity_classes=[create_zone_entities],
    )

    driver.config_manager = BaseConfigManager(
        get_config_path(driver.api.config_dir_path),
        driver.on_device_added,
        driver.on_device_removed,
        config_class=DeviceConfig,
    )

    await driver.register_all_device_instances()

    # Russound controllers do not announce themselves reliably, so setup uses manual entry.
    setup_handler = RussoundSetupFlow.create_handler(driver)

    await driver.api.init("driver.json", setup_handler)
    _LOG.info("Russound integration started")

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
