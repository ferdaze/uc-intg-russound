"""
Connection recovery tests for the Russound device layer.

Each test breaks the link to a mock RIO controller in a different way and
checks that the device comes back on its own, with live state updates.
"""

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "intg-russound"))

import device as device_module  # noqa: E402
import media_player as media_player_module  # noqa: E402
import ucapi  # noqa: E402
from const import DeviceConfig  # noqa: E402
from device import RussoundDevice  # noqa: E402
from media_player import RussoundZoneMediaPlayer  # noqa: E402
from mock_rio_server import MockRioServer  # noqa: E402
from ucapi import media_player  # noqa: E402
from ucapi_framework import DeviceEvents  # noqa: E402


async def wait_for(predicate, timeout: float = 8.0) -> bool:
    """Poll until ``predicate()`` is true or the timeout expires."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


@pytest.fixture(autouse=True)
def fast_timers(monkeypatch):
    """Shrink retry and command timers so outage tests run in seconds."""
    monkeypatch.setattr(device_module, "RECONNECT_MIN_DELAY", 0.2)
    monkeypatch.setattr(device_module, "RECONNECT_MAX_DELAY", 0.4)
    monkeypatch.setattr(media_player_module, "COMMAND_TIMEOUT", 0.5)


@pytest_asyncio.fixture
async def server():
    """Start a mock RIO controller for the duration of a test."""
    mock = MockRioServer()
    await mock.start()
    yield mock
    await mock.stop()


def make_device(port: int) -> RussoundDevice:
    """Build a device pointed at the mock controller."""
    config = DeviceConfig(
        identifier="test_mca88", name="Test MCA-88", address="127.0.0.1", port=port
    )
    return RussoundDevice(config, asyncio.get_running_loop())


@pytest_asyncio.fixture
async def device(server):
    """Return a device connected to the mock controller."""
    dev = make_device(server.port)
    assert await dev.connect() is True
    yield dev
    await dev.disconnect()


class _StubApi:
    """Stands in for the integration API: no entity is configured on a Remote."""

    class configured_entities:  # noqa: N801 - mirrors the ucapi attribute name
        """Empty entity store."""

        @staticmethod
        def contains(_entity_id: str) -> bool:
            """Report every entity as not configured."""
            return False


def make_entity(dev: RussoundDevice, zone: str = "c1z1") -> RussoundZoneMediaPlayer:
    """Build a zone entity the way the driver does, without a Remote attached."""
    entity = RussoundZoneMediaPlayer(dev.device_config, dev, zone)
    entity._api = _StubApi()  # the framework sets this after construction
    return entity


async def assert_live_updates(dev: RussoundDevice, zone: str = "c1z3") -> None:
    """Prove notifications flow: a zone turned on must show up in cached state."""
    assert dev.get_media_player_attributes(zone).STATE == media_player.States.OFF
    await dev.zone_on(zone)
    assert await wait_for(
        lambda: dev.get_media_player_attributes(zone).STATE != media_player.States.OFF
    ), "no state update received after reconnect - subscriptions were not restored"


async def test_recovers_after_connection_drop(device, server):
    """A dropped TCP session must be re-established and re-subscribed."""
    events: list[str] = []
    device.events.on(DeviceEvents.DISCONNECTED, lambda *_: events.append("down"))
    device.events.on(DeviceEvents.CONNECTED, lambda *_: events.append("up"))

    await server.drop_connections()

    assert await wait_for(lambda: "down" in events), "disconnect was not reported"
    assert await wait_for(lambda: device.is_connected), "device never reconnected"
    assert events[:2] == ["down", "up"]
    assert server.connections == 2
    await assert_live_updates(device)


async def test_recovers_after_keep_alive_timeout(server, monkeypatch):
    """A controller that goes quiet must be detected by the keep-alive and recovered."""
    import aiorussound.rio.client as rio_client

    monkeypatch.setattr(rio_client, "KEEP_ALIVE_INTERVAL", 0.3)
    monkeypatch.setattr(rio_client, "TIMEOUT", 0.5)

    dev = make_device(server.port)
    try:
        assert await dev.connect() is True

        server.silent = True
        assert await wait_for(lambda: not dev.is_connected), "silence went unnoticed"
        server.silent = False

        assert await wait_for(lambda: dev.is_connected), "device never reconnected"
        assert await wait_for(
            lambda: server.open_connections == 1
        ), "the abandoned session was left open on the controller"
        await assert_live_updates(dev)
    finally:
        await dev.disconnect()


async def test_recovers_after_controller_outage(device, server):
    """The device must keep retrying while the controller is unreachable."""
    port = server.port
    await server.stop()
    assert await wait_for(lambda: not device.is_connected)

    # Stay down long enough for several failed attempts.
    await asyncio.sleep(1.5)
    assert not device.is_connected

    await server.start(port)
    assert await wait_for(lambda: device.is_connected), "device never reconnected"
    await assert_live_updates(device)


async def test_failed_first_connect_retries_in_background(server):
    """If the controller is down at startup, the device must connect once it is up."""
    port = server.port
    await server.stop()

    dev = make_device(port)
    try:
        assert await dev.connect() is False
        await asyncio.sleep(0.6)
        assert not dev.is_connected

        await server.start(port)
        assert await wait_for(lambda: dev.is_connected), "device never connected"
        assert dev.zone_ids == [f"c1z{n}" for n in range(1, 9)]
        await assert_live_updates(dev)
    finally:
        await dev.disconnect()


async def test_connect_while_retrying_does_not_start_a_second_session(server):
    """Repeated connect() calls during an outage must not pile up connections."""
    port = server.port
    await server.stop()

    dev = make_device(port)
    try:
        assert await dev.connect() is False
        assert await dev.connect() is False
        assert await dev.connect() is False

        await server.start(port)
        assert await wait_for(lambda: dev.is_connected)
        await asyncio.sleep(1.0)
        assert server.connections == 1
        assert await dev.connect() is True
        assert server.connections == 1
    finally:
        await dev.disconnect()


async def test_disconnect_stops_retrying(server):
    """After disconnect() the device must leave the controller alone."""
    port = server.port
    await server.stop()

    dev = make_device(port)
    assert await dev.connect() is False
    await dev.disconnect()

    await server.start(port)
    await asyncio.sleep(1.5)
    assert not dev.is_connected
    assert server.connections == 0


async def test_disconnect_then_connect_works_again(device, server):
    """The standby cycle: disconnect, then a fresh connect with live updates."""
    await device.disconnect()
    assert not device.is_connected
    assert await wait_for(
        lambda: server.open_connections == 0
    ), "disconnect() left the session open on the controller"

    assert await device.connect() is True
    assert device.is_connected
    await assert_live_updates(device)


async def test_unanswered_command_times_out_and_recovers(device, server):
    """A command the controller never answers must not hang, and must self-heal."""
    entity = make_entity(device)

    server.silent = True
    status = await asyncio.wait_for(
        entity.handle_command(entity, media_player.Commands.ON, None), timeout=3
    )
    assert status == ucapi.StatusCodes.TIMEOUT

    server.silent = False
    assert await wait_for(lambda: device.is_connected), "device never reconnected"
    assert server.connections == 2
    assert await wait_for(
        lambda: server.open_connections == 1
    ), "the abandoned session was left open on the controller"

    status = await entity.handle_command(entity, media_player.Commands.ON, None)
    assert status == ucapi.StatusCodes.OK
    assert await wait_for(lambda: server.zones[1]["status"] == "ON")


async def test_command_while_disconnected_is_rejected(device, server):
    """Commands during an outage must fail fast with a clear status."""
    entity = make_entity(device)
    await server.stop()
    assert await wait_for(lambda: not device.is_connected)

    status = await asyncio.wait_for(
        entity.handle_command(entity, media_player.Commands.ON, None), timeout=2
    )
    assert status == ucapi.StatusCodes.SERVICE_UNAVAILABLE
