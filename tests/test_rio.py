"""Tests for the RIO protocol client and system discovery."""

import asyncio

import pytest
from fake_russound import FakeRussound
from rio import RioClient, RioCommandError, RioConnectionError, RioMessage, parse_line, split_key
from russound import discover_system, parse_source_branch, parse_zone_branch, version_tuple


def test_parse_line():
    assert parse_line('S VERSION="1.10.00"') == RioMessage("S", "VERSION", "1.10.00")
    assert parse_line("S") == RioMessage("S")
    assert parse_line('N C[1].Z[2].volume="25"\r\n') == RioMessage("N", "C[1].Z[2].volume", "25")
    assert parse_line('N S[1].songName="Say "Hello""') == RioMessage("N", "S[1].songName", 'Say "Hello"')
    assert parse_line('N C[1].Z[1].name=""') == RioMessage("N", "C[1].Z[1].name", "")
    assert parse_line("E Invalid Command") == RioMessage("E", None, "Invalid Command")
    assert parse_line("") is None
    assert parse_line("garbage") is None


def test_keys_and_versions():
    assert split_key("C[1].Z[2].volume") == ("C[1].Z[2]", "volume")
    assert split_key("VERSION") == ("", "VERSION")
    assert parse_zone_branch("C[2].Z[7]") == (2, 7)
    assert parse_zone_branch("S[3]") is None
    assert parse_source_branch("S[3]") == 3
    assert version_tuple("1.10.00") > version_tuple("1.09.00")
    assert version_tuple(None) == (0,)


def test_client_requests_and_notifications():
    async def scenario():
        server = FakeRussound()
        await server.start()
        notifications = []
        client = RioClient("127.0.0.1", server.port, on_notification=lambda k, v: notifications.append((k, v)))
        try:
            await client.connect()
            assert client.connected
            assert await client.version() == "1.10.00"
            assert await client.get("C[1].Z[3].name") == "Zone 3"
            with pytest.raises(RioCommandError):
                await client.get("C[1].Z[9].name")

            await client.watch("C[1].Z[1]")
            await client.event("C[1].Z[1]", "KeyPress", "Volume", 33)
            await asyncio.sleep(0.05)
            assert ("C[1].Z[1].volume", "33") in notifications
        finally:
            await client.close()
            await server.stop()
        assert not client.connected

    asyncio.run(scenario())


def test_client_detects_connection_loss():
    async def scenario():
        server = FakeRussound()
        await server.start()
        client = RioClient("127.0.0.1", server.port)
        try:
            await client.connect()
            server.drop_clients()
            await asyncio.wait_for(client.wait_closed(), 2)
            with pytest.raises(RioConnectionError):
                await client.version()
        finally:
            await client.close()
            await server.stop()

    asyncio.run(scenario())


def test_connect_refused():
    async def scenario():
        server = FakeRussound()
        await server.start()
        port = server.port
        await server.stop()
        with pytest.raises(RioConnectionError):
            await RioClient("127.0.0.1", port).connect()

    asyncio.run(scenario())


def test_discover_system():
    async def scenario():
        server = FakeRussound()
        await server.start()
        client = RioClient("127.0.0.1", server.port, keepalive_interval=None)
        try:
            await client.connect()
            system = await discover_system(client)
        finally:
            await client.close()
            await server.stop()

        assert system.rio_version == "1.10.00"
        assert system.primary.type == "MCA-88"
        assert system.primary.mac_address == "00:21:C7:0A:0B:0C"
        assert len(system.controllers) == 1
        assert [(z.controller, z.zone, z.name) for z in system.zones][:2] == [(1, 1, "Zone 1"), (1, 2, "Zone 2")]
        assert len(system.zones) == 8
        assert system.sources == {n: f"Source {n}" for n in range(1, 9)}

    asyncio.run(scenario())
