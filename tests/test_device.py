"""
End-to-end tests for the Russound device layer against a mock RIO server.

Run with::

    pip install -r test-requirements.txt
    pytest
"""

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "intg-russound"))

from const import DeviceConfig, russound_to_uc_volume  # noqa: E402
from device import RussoundDevice  # noqa: E402
from mock_rio_server import MockRioServer  # noqa: E402
from ucapi import media_player  # noqa: E402


@pytest_asyncio.fixture
async def server():
    """Start a mock RIO controller for the duration of a test."""
    mock = MockRioServer()
    await mock.start()
    yield mock
    await mock.stop()


@pytest_asyncio.fixture
async def connected_device(server):
    """Return a RussoundDevice connected to the mock controller."""
    config = DeviceConfig(
        identifier="test_mca88",
        name="Test MCA-88",
        address="127.0.0.1",
        port=server.port,
    )
    device = RussoundDevice(config, asyncio.get_running_loop())
    assert await device.connect() is True
    yield device
    await device.disconnect()


@pytest.mark.asyncio
async def test_connects_and_finds_all_zones(connected_device):
    """A full connect should expose all eight MCA-88 zones."""
    assert connected_device.is_connected
    assert connected_device.zone_ids == [f"c1z{n}" for n in range(1, 9)]
    assert connected_device.zone_name("c1z3") == "Zone 3"


@pytest.mark.asyncio
async def test_attributes_populated_for_each_zone(connected_device):
    """Every zone should have a cached attribute set after connecting."""
    attributes = connected_device.get_media_player_attributes("c1z1")
    assert attributes is not None
    assert attributes.STATE == media_player.States.OFF
    assert attributes.VOLUME == russound_to_uc_volume(20)
    assert attributes.MUTED is False
    assert attributes.SOURCE == "Sonos"
    assert "Turntable" in attributes.SOURCE_LIST


@pytest.mark.asyncio
async def test_zone_on_updates_state(connected_device, server):
    """Turning a zone on should be reflected back through the RIO notification."""
    await connected_device.zone_on("c1z2")
    await asyncio.sleep(0.2)

    assert any("!ZoneOn" in cmd for cmd in server.received)
    attributes = connected_device.get_media_player_attributes("c1z2")
    # Zone 2's source reports "playing", so the state resolves past plain ON.
    assert attributes.STATE == media_player.States.PLAYING


@pytest.mark.asyncio
async def test_volume_is_scaled_to_the_rio_range(connected_device, server):
    """A Remote volume of 100 must arrive at the controller as RIO volume 50."""
    await connected_device.set_volume("c1z1", 100)
    await asyncio.sleep(0.2)

    assert any(cmd.endswith("!KeyPress Volume 50") for cmd in server.received)
    assert server.zones[1]["volume"] == "50"

    await connected_device.set_volume("c1z1", 50)
    await asyncio.sleep(0.2)
    assert server.zones[1]["volume"] == "25"


@pytest.mark.asyncio
async def test_mute_and_source_selection(connected_device, server):
    """Mute and source selection should reach the controller."""
    await connected_device.mute("c1z1")
    await asyncio.sleep(0.2)
    assert server.zones[1]["mute"] == "ON"

    assert await connected_device.select_source("c1z1", "TV Audio") is True
    await asyncio.sleep(0.2)
    assert server.zones[1]["currentSource"] == "3"

    assert await connected_device.select_source("c1z1", "Nonexistent") is False


@pytest.mark.asyncio
async def test_simple_commands(connected_device, server):
    """Simple commands should map onto the right RIO events."""
    assert await connected_device.simple_command("c1z1", "ALL_ZONES_OFF") is True
    await asyncio.sleep(0.2)
    assert all(zone["status"] == "OFF" for zone in server.zones.values())

    assert await connected_device.simple_command("c1z1", "BASS_UP") is True
    await asyncio.sleep(0.2)
    assert server.zones[1]["bass"] == "2"

    assert await connected_device.simple_command("c1z1", "NOT_A_COMMAND") is False


@pytest.mark.asyncio
async def test_unknown_zone_is_handled(connected_device):
    """Commands for a zone that does not exist must not raise."""
    await connected_device.zone_on("c9z9")
    assert connected_device.zone("c9z9") is None
    assert connected_device.zone("garbage") is None
