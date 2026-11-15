"""
Setup flow for the Russound RIO integration.

:copyright: (c) 2026 by Jeff Ferdinandsen.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any

from aiorussound import RussoundTcpConnectionHandler
from aiorussound.rio import RussoundRIOClient
from const import CONNECT_TIMEOUT, DEFAULT_PORT, DeviceConfig, zone_sub_id
from ucapi import IntegrationSetupError, RequestUserInput, SetupError
from ucapi_framework import BaseSetupFlow, DiscoveredDevice

_LOG = logging.getLogger(__name__)


class RussoundSetupFlow(BaseSetupFlow[DeviceConfig]):
    """Guides the user through adding a Russound controller."""

    def get_manual_entry_form(self) -> RequestUserInput:
        """Return the manual host/port entry form."""
        return RequestUserInput(
            {"en": "Russound controller"},
            [
                {
                    "id": "info",
                    "label": {"en": "Connection details"},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "Enter the IP address of your Russound "
                                    "controller. RIO must be enabled and the "
                                    "controller must be on the same network as "
                                    "the Remote. The default RIO port is 9621."
                                )
                            }
                        }
                    },
                },
                {
                    "id": "name",
                    "label": {"en": "Name (optional)"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "address",
                    "label": {"en": "IP address or hostname"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "port",
                    "label": {"en": "RIO port"},
                    "field": {
                        "number": {"value": DEFAULT_PORT, "min": 1, "max": 65535}
                    },
                },
            ],
        )

    def format_discovered_device_label(self, device: DiscoveredDevice) -> str:
        """Render a discovered controller in the selection list."""
        model = (device.extra_data or {}).get("model", "Russound")
        return f"{model} [{device.address}]"

    def get_device_id(self, device_config: DeviceConfig) -> str:
        """Return the unique id of a configured controller."""
        return device_config.identifier

    def get_device_name(self, device_config: DeviceConfig) -> str:
        """Return the friendly name of a configured controller."""
        return device_config.name

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> DeviceConfig | SetupError | RequestUserInput:
        """
        Validate the entered connection details against the live controller.

        Connects over RIO, reads the controller model, MAC address and zone
        names, then builds the persisted configuration.
        """
        address = str(input_values.get("address", "")).strip()
        name = str(input_values.get("name", "")).strip()

        try:
            port = int(input_values.get("port") or DEFAULT_PORT)
        except (TypeError, ValueError):
            port = DEFAULT_PORT

        if not address:
            _LOG.warning("No address entered, re-showing the form")
            return self.get_manual_entry_form()

        _LOG.info("Validating Russound controller at %s:%s", address, port)

        client = RussoundRIOClient(RussoundTcpConnectionHandler(address, port))
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await client.connect()

            controller = client.controllers.get(1)
            if controller is None:
                _LOG.error("No primary controller reported by %s", address)
                return SetupError(IntegrationSetupError.NOT_FOUND)

            await client.load_zone_source_metadata()

            model = controller.controller_type or "Russound"
            identifier = controller.mac_address or f"{address}_{port}".replace(".", "_")

            zone_names = {}
            for controller_id, ctrl in client.controllers.items():
                for zone_id, zone in ctrl.zones.items():
                    sub_id = zone_sub_id(controller_id, zone_id)
                    zone_names[sub_id] = zone.name or f"Zone {zone_id}"

            _LOG.info(
                "Found %s (RIO v%s) with %d zone(s)",
                model,
                client.rio_version,
                len(zone_names),
            )

            return DeviceConfig(
                identifier=identifier,
                name=name or model,
                address=address,
                port=port,
                model=model,
                zone_names=zone_names,
            )

        except (TimeoutError, asyncio.TimeoutError):
            _LOG.error("Timeout connecting to %s:%s", address, port)
            return SetupError(IntegrationSetupError.TIMEOUT)
        except (ConnectionError, OSError) as err:
            _LOG.error("Cannot reach %s:%s - %s", address, port, err)
            return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("Setup failed for %s:%s - %s", address, port, err)
            return SetupError(IntegrationSetupError.NOT_FOUND)
        finally:
            try:
                await client.disconnect()
            except Exception:  # pylint: disable=broad-except
                pass
            reconnect_task = getattr(client, "_reconnect_task", None)
            if reconnect_task is not None and not reconnect_task.done():
                reconnect_task.cancel()
