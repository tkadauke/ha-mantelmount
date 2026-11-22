"""Tests for the MantelMount config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mantelmount.api import DeviceInfo, MantelMountTimeoutError
from custom_components.mantelmount.const import DOMAIN

from .conftest import HOST, MAC

DHCP_INFO = DhcpServiceInfo(ip="10.0.0.21", hostname="mantelmount_8436fe", macaddress="d83af58436fe")


async def test_user_step_should_create_entry_named_after_host_name(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: f" {HOST} "})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "MantelMount 8436fe"
    assert result["data"] == {CONF_HOST: HOST}
    assert result["result"].unique_id == MAC


async def test_user_step_should_show_error_if_mount_does_not_answer(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    mock_client.async_get_status.side_effect = MantelMountTimeoutError("no reply")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_step_should_update_host_if_mount_is_already_configured(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "10.0.0.99"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "10.0.0.99"


async def test_dhcp_step_should_ask_for_confirmation_then_create_entry(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP_INFO)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "10.0.0.21"}
    assert result["result"].unique_id == MAC


async def test_dhcp_step_should_follow_new_address_of_configured_mount(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP_INFO)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "10.0.0.21"


async def test_dhcp_step_should_abort_if_mount_does_not_answer(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    mock_client.async_get_status.side_effect = MantelMountTimeoutError("no reply")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP_INFO)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_reconfigure_step_should_update_host(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "10.0.0.30"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_HOST] == "10.0.0.30"


async def test_reconfigure_step_should_refuse_a_different_mount(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_client.async_get_device_info.return_value = DeviceInfo(mac="d8:3a:f5:a0:17:1d", host_name="MantelMount_a0171d")
    result = await config_entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "10.0.0.30"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert config_entry.data[CONF_HOST] == HOST
