"""
Setup Flow Module.

Asks for the controller address, discovers the Russound system over RIO and lets the
user choose which zones to expose as media player entities.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
import re
from typing import Any

from const import DEFAULT_PORT, DeviceConfig, ZoneConfig
from rio import RioClient, RioCommandError, RioConnectionError
from russound import discover_system
from ucapi import IntegrationSetupError, RequestUserInput, SetupError, UserDataResponse
from ucapi_framework import BaseSetupFlow

_LOG = logging.getLogger(__name__)

_ZONE_FIELD_PREFIX = "zone_"


def make_identifier(mac_address: str | None, address: str) -> str:
    """Build a stable identifier (no dots, safe for entity ids) from the MAC or address."""
    source = mac_address or address
    return re.sub(r"[^0-9a-zA-Z]", "", source).lower() or "russound"


def _is_checked(value: Any) -> bool:
    """Checkbox values arrive as booleans or as the strings "true"/"false"."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "on", "yes")


def _zone_field_id(zone: ZoneConfig) -> str:
    return f"{_ZONE_FIELD_PREFIX}{zone.key}"


class RussoundSetupFlow(BaseSetupFlow[DeviceConfig]):
    """Setup flow for Russound controllers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the setup flow."""
        super().__init__(*args, **kwargs)
        self._discovered_zones: list[ZoneConfig] = []

    def get_manual_entry_form(self) -> RequestUserInput:
        """Return the form asking for the controller's network address."""
        existing = self.selected_config_entry
        return RequestUserInput(
            {"en": "Russound Controller"},
            [
                {
                    "id": "info",
                    "label": {"en": "Setup your Russound controller"},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "Enter the IP address of your Russound MCA-88 (or other RIO capable "
                                    "controller). The controller must be on the same network as the Remote "
                                    "and have a static or reserved IP address. RIO uses TCP port 9621."
                                ),
                            }
                        }
                    },
                },
                {
                    "field": {"text": {"value": existing.address if existing else ""}},
                    "id": "address",
                    "label": {"en": "IP Address or Hostname"},
                },
                {
                    "field": {
                        "number": {
                            "value": existing.port if existing else DEFAULT_PORT,
                            "min": 1,
                            "max": 65535,
                        }
                    },
                    "id": "port",
                    "label": {"en": "RIO Port"},
                },
                {
                    "field": {"text": {"value": existing.name if existing else ""}},
                    "id": "name",
                    "label": {"en": "Name (optional)"},
                },
            ],
        )

    async def query_device(self, input_values: dict[str, Any]) -> DeviceConfig | SetupError | RequestUserInput:
        """
        Connect to the controller and discover its zones and sources.

        :param input_values: Values from the manual entry form
        :return: DeviceConfig with all zones, or SetupError
        """
        address = str(input_values.get("address", "")).strip()
        name = str(input_values.get("name", "")).strip()
        try:
            port = int(input_values.get("port") or DEFAULT_PORT)
        except (TypeError, ValueError):
            port = DEFAULT_PORT

        if not address:
            _LOG.warning("Address is required, re-displaying form")
            return self.get_manual_entry_form()

        _LOG.info("Querying Russound controller at %s:%d", address, port)
        client = RioClient(address, port, keepalive_interval=None)
        try:
            await client.connect()
            system = await discover_system(client)
        except RioConnectionError as ex:
            _LOG.error("Cannot connect to %s:%d: %s", address, port, ex)
            return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
        except RioCommandError as ex:
            _LOG.error("Controller at %s did not answer as expected: %s", address, ex)
            return SetupError(IntegrationSetupError.NOT_FOUND)
        finally:
            await client.close()

        if not system.zones:
            _LOG.error("No zones found on controller at %s", address)
            return SetupError(IntegrationSetupError.NOT_FOUND)

        primary = system.primary
        self._discovered_zones = [ZoneConfig(zone.controller, zone.zone, zone.name) for zone in system.zones]
        return DeviceConfig(
            identifier=make_identifier(primary.mac_address, address),
            name=name or f"Russound {primary.type}",
            address=address,
            port=port,
            model=primary.type,
            zones=list(self._discovered_zones),
        )

    async def get_additional_configuration_screen(
        self, device_config: DeviceConfig, previous_input: dict[str, Any]
    ) -> RequestUserInput | None:
        """Show one checkbox per discovered zone."""
        _ = previous_input
        return self._zone_selection_screen(device_config)

    def _zone_selection_screen(self, device_config: DeviceConfig, error: str | None = None) -> RequestUserInput:
        previous = self.selected_config_entry
        previously_enabled = {zone.key for zone in previous.zones} if previous else None

        multiple_controllers = len({zone.controller for zone in self._discovered_zones}) > 1
        text = f"Found {len(self._discovered_zones)} zone(s) on your {device_config.model}. "
        text += "Select the zones to add to the Remote. Each zone becomes a media player entity."
        if error:
            text = f"{error}\n\n{text}"

        fields: list[dict[str, Any]] = [
            {
                "id": "zones_info",
                "label": {"en": "Zones"},
                "field": {"label": {"value": {"en": text}}},
            }
        ]
        for zone in self._discovered_zones:
            label = f"Zone {zone.zone}: {zone.name}"
            if multiple_controllers:
                label = f"Controller {zone.controller} {label}"
            checked = previously_enabled is None or zone.key in previously_enabled
            fields.append(
                {
                    "id": _zone_field_id(zone),
                    "label": {"en": label},
                    "field": {"checkbox": {"value": checked}},
                }
            )
        return RequestUserInput({"en": "Select Zones"}, fields)

    async def handle_additional_configuration_response(
        self, msg: UserDataResponse
    ) -> DeviceConfig | SetupError | RequestUserInput | None:
        """Keep only the selected zones."""
        config = self._pending_device_config
        if config is None:
            return SetupError(IntegrationSetupError.OTHER)

        selected = [
            zone for zone in self._discovered_zones if _is_checked(msg.input_values.get(_zone_field_id(zone), False))
        ]
        if not selected:
            return self._zone_selection_screen(config, error="Please select at least one zone.")

        config.zones = selected
        _LOG.info("Configured zones: %s", ", ".join(zone.name for zone in selected))
        return config
