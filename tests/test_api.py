"""Tests for the adapter protocol client."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mantelmount.api import (
    AlpsSettings,
    Jog,
    MantelMountClient,
    MantelMountResponseError,
    MantelMountTimeoutError,
    MountPosition,
    MountStatus,
    SettingsForm,
    SmoothStart,
    parse_alps_settings,
    parse_device_info,
)

from .conftest import STATUS_REPLY, fixture_text


@dataclass
class FakeAdapter(asyncio.DatagramProtocol):
    """A UDP server that answers like the adapter, optionally ignoring the first datagrams."""

    respond: Callable[[str], str | None]
    ignore_first: int = 0
    received: list[str] = field(default_factory=list)
    transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str | int, ...]) -> None:
        self.received.append(data.decode())
        if len(self.received) <= self.ignore_first:
            return
        reply = self.respond(data.decode())
        if reply is not None and self.transport is not None:
            self.transport.sendto(reply.encode(), addr)


def adapter_reply(command: str) -> str:
    """Answer the way the real adapter does: status for MMQ, an echoed prefix otherwise."""
    return STATUS_REPLY if command.startswith("MMQ") else command[:3] + "\r"


@pytest.fixture
async def session(aioclient_mock: AiohttpClientMocker) -> AsyncGenerator[aiohttp.ClientSession]:
    client_session = aioclient_mock.create_session(asyncio.get_running_loop())
    yield client_session
    await client_session.close()


@pytest.fixture
async def adapter(socket_enabled: None) -> AsyncGenerator[FakeAdapter]:
    loop = asyncio.get_running_loop()
    protocol = FakeAdapter(respond=adapter_reply)
    transport, _ = await loop.create_datagram_endpoint(lambda: protocol, local_addr=("127.0.0.1", 0))
    yield protocol
    transport.close()


def udp_client(adapter: FakeAdapter, session: aiohttp.ClientSession) -> MantelMountClient:
    assert adapter.transport is not None
    port = adapter.transport.get_extra_info("sockname")[1]
    return MantelMountClient("127.0.0.1", session, udp_port=port, timeout=0.2)


def test_status_should_parse_reply_from_real_adapter() -> None:
    status = MountStatus.parse(STATUS_REPLY)

    assert status.firmware_version == 693
    assert status.tv_current == 69
    assert status.temperature == 33
    assert status.left_at_limit and status.right_at_limit
    assert not status.tv_on
    assert not status.position_lost


def test_status_should_keep_last_segment_if_reply_is_echoed() -> None:
    status = MountStatus.parse("MMQ" + STATUS_REPLY.replace(",69,", ",70,"))

    assert status.tv_current == 70


@pytest.mark.parametrize("reply", ["MMJ\r", "MMQ0,0,0\r", "MMQ0,0,0,0,0,0,x,0,0,693,0,69,1,1,0,4\r"])
def test_status_should_reject_malformed_reply(reply: str) -> None:
    with pytest.raises(MantelMountResponseError):
        MountStatus.parse(reply)


def test_position_should_parse_ajax_reply() -> None:
    position = MountPosition.parse('["-2.06","-98.65","Normal","On","1070"] ')

    assert position == MountPosition(
        azimuth=-2.06, elevation=-98.65, temperature_status="Normal", tv_on=True, tv_current=1070
    )
    assert not position.is_home


def test_position_should_be_home_if_stowed() -> None:
    assert MountPosition.parse('["0.00","0.00","Normal","Off","67"]').is_home


def test_position_should_reject_empty_values() -> None:
    with pytest.raises(MantelMountResponseError):
        MountPosition.parse('["","","","",""]')


def test_settings_form_should_collect_fields_like_a_browser() -> None:
    fields = SettingsForm.parse(fixture_text("device.shtml"))

    assert fields["stabrel"] == "0"
    assert fields["enable_alps"] == "1"
    assert fields["curon"] == "250"
    assert fields["curoff"] == "150"
    assert "cazim" in fields


def test_settings_form_should_reject_page_without_settings() -> None:
    with pytest.raises(MantelMountResponseError):
        SettingsForm.parse(fixture_text("network.shtml"))


def test_alps_settings_should_parse_form_fields() -> None:
    settings = parse_alps_settings(SettingsForm.parse(fixture_text("device.shtml")))

    assert settings == AlpsSettings(
        enabled=True, tv_on_threshold=250, tv_off_threshold=150, smooth_start=SmoothStart.NONE
    )


def test_device_info_should_read_mac_and_host_name() -> None:
    info = parse_device_info(fixture_text("network.shtml"))

    assert info.mac == "d8:3a:f5:84:36:fe"
    assert info.host_name == "MantelMount_8436fe"


async def test_status_query_should_send_carriage_return_terminated_command(
    adapter: FakeAdapter, session: aiohttp.ClientSession
) -> None:
    status = await udp_client(adapter, session).async_get_status()

    assert adapter.received == ["MMQ\r"]
    assert status.firmware_version == 693


async def test_command_should_retry_if_reply_is_lost(adapter: FakeAdapter, session: aiohttp.ClientSession) -> None:
    adapter.ignore_first = 2

    await udp_client(adapter, session).async_recall_preset(0)

    assert adapter.received == ["MMR0\r"] * 3


async def test_command_should_fail_if_adapter_never_answers(
    adapter: FakeAdapter, session: aiohttp.ClientSession
) -> None:
    adapter.ignore_first = 10

    with pytest.raises(MantelMountTimeoutError):
        await udp_client(adapter, session).async_recall_preset(2)
    assert len(adapter.received) == 3


async def test_jog_should_not_retry_if_reply_is_lost(adapter: FakeAdapter, session: aiohttp.ClientSession) -> None:
    adapter.ignore_first = 1

    with pytest.raises(MantelMountTimeoutError):
        await udp_client(adapter, session).async_jog(Jog.UP)
    assert adapter.received == ["MMJ2\r"]


async def test_command_should_reject_unexpected_reply(adapter: FakeAdapter, session: aiohttp.ClientSession) -> None:
    adapter.respond = lambda command: "MMX\r"

    with pytest.raises(MantelMountResponseError):
        await udp_client(adapter, session).async_save_preset(1)


@pytest.mark.parametrize(("method", "preset"), [("async_recall_preset", 4), ("async_save_preset", 0)])
async def test_preset_commands_should_reject_unknown_presets(
    adapter: FakeAdapter, session: aiohttp.ClientSession, method: str, preset: int
) -> None:
    with pytest.raises(ValueError):
        await getattr(udp_client(adapter, session), method)(preset)
    assert adapter.received == []


async def test_stop_should_send_jog_zero(adapter: FakeAdapter, session: aiohttp.ClientSession) -> None:
    await udp_client(adapter, session).async_stop()

    assert adapter.received == ["MMJ0\r"]


async def test_position_should_be_read_from_ajax_page(
    aioclient_mock: AiohttpClientMocker, session: aiohttp.ClientSession
) -> None:
    aioclient_mock.get(
        "http://10.0.0.20/ajax.shtml?var=cazim,celev,temp,tvstat,curcur", text='["0.00","0.00","Normal","Off","67"] '
    )
    client = MantelMountClient("10.0.0.20", session)

    position = await client.async_get_position()

    assert position.tv_current == 67


async def test_set_alps_settings_should_post_whole_form_with_changed_value(
    aioclient_mock: AiohttpClientMocker, session: aiohttp.ClientSession
) -> None:
    page = fixture_text("device.shtml")
    aioclient_mock.get("http://10.0.0.20/device.shtml", text=page)
    aioclient_mock.post("http://10.0.0.20/save_device.xml", text="ok")
    client = MantelMountClient("10.0.0.20", session)

    with pytest.raises(MantelMountResponseError):
        await client.async_set_alps_settings(tv_on_threshold=300)

    fields = next(call[2] for call in aioclient_mock.mock_calls if call[0] == "POST")
    assert fields["curon"] == "300"
    assert fields["curoff"] == "150"
    assert fields["enable_alps"] == "1"
    assert fields["stabrel"] == "0"


async def test_set_alps_settings_should_return_settings_adapter_confirms(
    aioclient_mock: AiohttpClientMocker, session: aiohttp.ClientSession
) -> None:
    aioclient_mock.get("http://10.0.0.20/device.shtml", text=fixture_text("device.shtml"))
    aioclient_mock.post("http://10.0.0.20/save_device.xml", text="ok")
    client = MantelMountClient("10.0.0.20", session)

    settings = await client.async_set_alps_settings(tv_on_threshold=250)

    assert settings == AlpsSettings(
        enabled=True, tv_on_threshold=250, tv_off_threshold=150, smooth_start=SmoothStart.NONE
    )
    assert [call[0] for call in aioclient_mock.mock_calls] == ["GET", "POST", "GET"]


async def test_set_alps_settings_should_refuse_on_threshold_below_off_threshold(
    aioclient_mock: AiohttpClientMocker, session: aiohttp.ClientSession
) -> None:
    aioclient_mock.get("http://10.0.0.20/device.shtml", text=fixture_text("device.shtml"))
    client = MantelMountClient("10.0.0.20", session)

    with pytest.raises(ValueError):
        await client.async_set_alps_settings(tv_on_threshold=100)
    assert not any(call[0] == "POST" for call in aioclient_mock.mock_calls)
