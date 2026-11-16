"""
End-to-end tests through the real integration driver.

These drive the framework the way the Remote does (start up, subscribe to an
entity, send ``connect``) and check the entity state the Remote would see.
"""

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "intg-russound"))

import device as device_module  # noqa: E402
from const import DeviceConfig  # noqa: E402
from driver import create_driver  # noqa: E402
from mock_rio_server import MockRioServer  # noqa: E402
from test_reconnect import wait_for  # noqa: E402
from ucapi import media_player  # noqa: E402
from ucapi_framework import BaseConfigManager  # noqa: E402

DEVICE_ID = "00:21:C7:00:BF:3C"
ZONE_NAMES = {f"c1z{n}": f"Zone {n}" for n in range(1, 9)}
ENTITY_ID = f"media_player.{DEVICE_ID}.c1z4"


@pytest.fixture(autouse=True)
def fast_timers(monkeypatch):
    """Shrink retry timers so outage tests run in seconds."""
    monkeypatch.setattr(device_module, "RECONNECT_MIN_DELAY", 0.2)
    monkeypatch.setattr(device_module, "RECONNECT_MAX_DELAY", 0.4)


@pytest_asyncio.fixture
async def server():
    """Start a mock RIO controller for the duration of a test."""
    mock = MockRioServer()
    await mock.start()
    yield mock
    await mock.stop()


@pytest_asyncio.fixture
async def driver(server, tmp_path):
    """
    Start the driver with one stored controller, as after a Remote reboot.

    The stored configuration carries the zone names saved by the setup flow.
    """
    drv = create_driver(asyncio.get_running_loop())
    drv.config_manager = BaseConfigManager(
        str(tmp_path),
        drv.on_device_added,
        drv.on_device_removed,
        config_class=DeviceConfig,
    )
    drv.config_manager.add_or_update(
        DeviceConfig(
            identifier=DEVICE_ID,
            name="Test MCA-88",
            address="127.0.0.1",
            port=server.port,
            model="MCA-88",
            zone_names=dict(ZONE_NAMES),
        )
    )
    await drv.register_all_configured_devices()
    yield drv
    for dev in list(drv._device_instances.values()):
        await dev.disconnect()


async def remote_subscribes_and_connects(drv) -> None:
    """Replay what the Remote sends after it connects to the driver."""
    entity = drv.api.available_entities.get(ENTITY_ID)
    assert entity is not None, "zone entity was not registered at startup"
    drv.api.configured_entities.add(entity)
    await drv.on_subscribe_entities([ENTITY_ID])
    await drv.on_r2_connect_cmd()


def remote_state(drv) -> str:
    """Return the entity state as the Remote currently sees it."""
    entity = drv.api.configured_entities.get(ENTITY_ID)
    return entity.attributes[media_player.Attributes.STATE]


async def test_entities_exist_before_the_controller_answers(server, driver):
    """All eight zones must be offered to the Remote straight after startup."""
    ids = [f"media_player.{DEVICE_ID}.c1z{n}" for n in range(1, 9)]
    assert all(driver.api.available_entities.get(eid) is not None for eid in ids)
    assert server.connections == 0


async def test_entity_recovers_after_connection_drop(server, driver):
    """The Remote must see the zone go unavailable and then come back."""
    await remote_subscribes_and_connects(driver)
    assert await wait_for(lambda: remote_state(driver) == media_player.States.OFF)

    await server.drop_connections()
    assert await wait_for(
        lambda: remote_state(driver) == media_player.States.UNAVAILABLE
    ), "the Remote was not told the zone is unavailable"
    assert await wait_for(
        lambda: remote_state(driver) == media_player.States.OFF
    ), "the zone stayed unavailable after the controller came back"

    # State changes must reach the Remote again, not just the reconnect itself.
    dev = driver._device_instances[DEVICE_ID]
    await dev.zone_on("c1z4")
    assert await wait_for(
        lambda: remote_state(driver)
        not in (media_player.States.OFF, media_player.States.UNAVAILABLE)
    ), "zone state changes are not reaching the Remote after the reconnect"


async def test_entity_recovers_when_controller_is_down_at_startup(server, tmp_path):
    """A controller that is off when the Remote boots must be picked up later."""
    port = server.port
    await server.stop()

    drv = create_driver(asyncio.get_running_loop())
    drv.config_manager = BaseConfigManager(
        str(tmp_path),
        drv.on_device_added,
        drv.on_device_removed,
        config_class=DeviceConfig,
    )
    drv.config_manager.add_or_update(
        DeviceConfig(
            identifier=DEVICE_ID,
            name="Test MCA-88",
            address="127.0.0.1",
            port=port,
            model="MCA-88",
            zone_names=dict(ZONE_NAMES),
        )
    )
    try:
        await drv.register_all_configured_devices()
        await remote_subscribes_and_connects(drv)
        await asyncio.sleep(1.0)
        assert remote_state(drv) in (
            media_player.States.UNAVAILABLE,
            media_player.States.UNKNOWN,
        )

        await server.start(port)
        assert await wait_for(
            lambda: remote_state(drv) == media_player.States.OFF
        ), "the zone never became available after the controller came up"
    finally:
        for dev in list(drv._device_instances.values()):
            await dev.disconnect()


async def test_standby_cycle(server, driver):
    """Entering standby disconnects; leaving it reconnects with fresh state."""
    await remote_subscribes_and_connects(driver)
    assert await wait_for(lambda: remote_state(driver) == media_player.States.OFF)

    await driver.on_r2_enter_standby()
    assert await wait_for(lambda: server.open_connections == 0)

    await driver.on_r2_exit_standby()
    assert await wait_for(lambda: server.open_connections == 1)
    assert await wait_for(lambda: remote_state(driver) == media_player.States.OFF)
