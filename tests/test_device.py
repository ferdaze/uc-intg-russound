"""Tests for the Russound device (connection, state tracking and commands)."""

import asyncio

from const import DeviceConfig, ZoneConfig
from device import RussoundDevice
from fake_russound import FakeRussound
from media_player import RussoundZoneMediaPlayer, to_device_volume, to_ui_volume
from setup import make_identifier
from ucapi.media_player import States


async def wait_for(condition, timeout: float = 3.0) -> None:
    """Poll until condition() is true."""
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


def make_config(port: int) -> DeviceConfig:
    return DeviceConfig(
        identifier="0021c70a0b0c",
        name="Russound MCA-88",
        address="127.0.0.1",
        port=port,
        model="MCA-88",
        zones=[ZoneConfig(1, 1, "Kitchen"), ZoneConfig(1, 2, "Patio")],
    )


def test_volume_scaling():
    assert to_ui_volume(0) == 0
    assert to_ui_volume(25) == 50
    assert to_ui_volume(50) == 100
    assert to_device_volume(100) == 50
    assert to_device_volume(51) == 26
    assert to_device_volume(-5) == 0
    assert to_device_volume(250) == 50


def test_make_identifier():
    assert make_identifier("00:21:C7:0A:0B:0C", "192.168.1.20") == "0021c70a0b0c"
    assert make_identifier(None, "192.168.1.20") == "192168120"


def test_state_mapping():
    assert RussoundZoneMediaPlayer._map_state(False, "playing") == States.OFF  # pylint: disable=protected-access
    assert RussoundZoneMediaPlayer._map_state(True, None) == States.ON  # pylint: disable=protected-access
    assert RussoundZoneMediaPlayer._map_state(True, "playing") == States.PLAYING  # pylint: disable=protected-access
    assert RussoundZoneMediaPlayer._map_state(True, "paused") == States.PAUSED  # pylint: disable=protected-access


def test_device_tracks_state_and_sends_commands():
    async def scenario():
        server = FakeRussound()
        await server.start()
        device = RussoundDevice(make_config(server.port), loop=asyncio.get_running_loop())
        updates = []
        device.push_update = lambda: updates.append(1)  # type: ignore[method-assign]
        try:
            await device.connect()
            await wait_for(lambda: device.is_connected and device.zone(1, 2).known)

            kitchen = device.zone(1, 1)
            assert kitchen.name == "Zone 1"  # name reported by the controller wins
            assert kitchen.power is False
            assert kitchen.volume == 20
            assert device.source_names == [f"Source {n}" for n in range(1, 9)]
            assert updates

            await device.power_on(1, 1)
            await wait_for(lambda: kitchen.power is True)

            await device.set_volume(1, 1, 60)  # clamped to 50
            await wait_for(lambda: kitchen.volume == 50)
            await device.volume_down(1, 1)
            await wait_for(lambda: kitchen.volume == 49)

            await device.set_mute(1, 1, True)
            await wait_for(lambda: kitchen.muted is True)
            assert "EVENT C[1].Z[1]!ZoneMuteOn" in server.commands
            await device.mute_toggle(1, 1)
            await wait_for(lambda: kitchen.muted is False)

            await device.select_source(1, 1, device.source_number("source 3"))
            await wait_for(lambda: kitchen.source == 3)

            await device.adjust_tone(1, 1, "bass", 1)
            await wait_for(lambda: kitchen.bass == 1)
            await device.set_loudness(1, 1)
            await wait_for(lambda: kitchen.loudness is True)
            await device.reset_tone(1, 1)
            await wait_for(lambda: kitchen.bass == 0)

            # Patio was not touched
            assert device.zone(1, 2).power is False
            # Zones that are not configured are not watched
            assert "WATCH C[1].Z[3] ON" not in server.commands
        finally:
            await device.disconnect()
            await server.stop()
        assert not device.is_connected

    asyncio.run(scenario())


def test_old_firmware_mute_uses_toggle():
    async def scenario():
        server = FakeRussound(version="1.07.00")
        await server.start()
        device = RussoundDevice(make_config(server.port), loop=asyncio.get_running_loop())
        try:
            await device.connect()
            await wait_for(lambda: device.is_connected and device.zone(1, 1).known)
            await device.set_mute(1, 1, True)
            await wait_for(lambda: device.zone(1, 1).muted is True)
            await device.set_mute(1, 1, True)  # already muted: no toggle
            assert server.commands.count("EVENT C[1].Z[1]!KeyRelease Mute") == 1
        finally:
            await device.disconnect()
            await server.stop()

    asyncio.run(scenario())


def test_device_reconnects_after_connection_loss():
    async def scenario():
        server = FakeRussound()
        await server.start()
        device = RussoundDevice(make_config(server.port), loop=asyncio.get_running_loop())
        try:
            await device.connect()
            await wait_for(lambda: device.is_connected and device.zone(1, 1).known)

            server.drop_clients()
            await wait_for(lambda: not device.is_connected)
            await wait_for(lambda: not device.zone(1, 1).known)  # stale state is cleared

            await wait_for(lambda: device.is_connected and device.zone(1, 1).known, timeout=10)
        finally:
            await device.disconnect()
            await server.stop()

    asyncio.run(scenario())
