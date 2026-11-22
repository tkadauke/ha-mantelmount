"""Tests for setting up the integration and its entities."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.mantelmount.api import Jog, MantelMountTimeoutError, SmoothStart
from custom_components.mantelmount.const import IDLE_INTERVAL, MOVING_INTERVAL

from .conftest import LOWERED_POSITION, MAC, SETTINGS


async def setup_mount(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, interval=IDLE_INTERVAL) -> None:
    freezer.tick(interval)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.fixture
async def mount(hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry) -> MockConfigEntry:
    await setup_mount(hass, config_entry)
    return config_entry


async def test_setup_should_register_device_by_mac(
    hass: HomeAssistant, mount: MockConfigEntry, device_registry: dr.DeviceRegistry
) -> None:
    device = device_registry.async_get_device(connections={(dr.CONNECTION_NETWORK_MAC, MAC)})

    assert device is not None
    assert device.name == "MantelMount 8436fe"
    assert device.sw_version == "693"


async def test_setup_should_retry_if_mount_does_not_answer(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    mock_client.async_get_status.side_effect = MantelMountTimeoutError("no reply")
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_sensors_should_report_position_and_tv_current(hass: HomeAssistant, mount: MockConfigEntry) -> None:
    assert hass.states.get("sensor.mantelmount_8436fe_elevation").state == "0.0"
    assert hass.states.get("sensor.mantelmount_8436fe_swivel").state == "0.0"
    assert hass.states.get("sensor.mantelmount_8436fe_tv_current").state == "69"
    assert hass.states.get("sensor.mantelmount_8436fe_temperature_status").state == "Normal"


async def test_binary_sensors_should_report_stowed_mount_with_tv_off(
    hass: HomeAssistant, mount: MockConfigEntry
) -> None:
    assert hass.states.get("binary_sensor.mantelmount_8436fe_tv").state == STATE_OFF
    assert hass.states.get("binary_sensor.mantelmount_8436fe_at_home_position").state == STATE_ON
    assert hass.states.get("binary_sensor.mantelmount_8436fe_moving").state == STATE_OFF
    assert hass.states.get("binary_sensor.mantelmount_8436fe_position_lost").state == STATE_OFF


async def test_moving_should_turn_on_and_poll_faster_while_position_changes(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock, freezer: FrozenDateTimeFactory
) -> None:
    mock_client.async_get_position.return_value = LOWERED_POSITION

    await tick(hass, freezer)

    assert hass.states.get("binary_sensor.mantelmount_8436fe_moving").state == STATE_ON
    assert hass.states.get("binary_sensor.mantelmount_8436fe_tv").state == STATE_ON
    assert hass.states.get("sensor.mantelmount_8436fe_elevation").state == "-98.65"
    assert mount.runtime_data.update_interval == MOVING_INTERVAL


async def test_polling_should_slow_down_once_position_settles(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock, freezer: FrozenDateTimeFactory
) -> None:
    mock_client.async_get_position.return_value = LOWERED_POSITION
    await tick(hass, freezer)

    await tick(hass, freezer, MOVING_INTERVAL)

    assert hass.states.get("binary_sensor.mantelmount_8436fe_moving").state == STATE_OFF
    assert mount.runtime_data.update_interval == IDLE_INTERVAL


async def test_entities_should_become_unavailable_if_mount_stops_answering(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock, freezer: FrozenDateTimeFactory
) -> None:
    mock_client.async_get_status.side_effect = MantelMountTimeoutError("no reply")

    await tick(hass, freezer)

    assert hass.states.get("sensor.mantelmount_8436fe_elevation").state == STATE_UNAVAILABLE


async def test_settings_should_be_reread_only_every_few_minutes(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock, freezer: FrozenDateTimeFactory
) -> None:
    await tick(hass, freezer)
    await tick(hass, freezer)

    assert mock_client.async_get_alps_settings.await_count == 1


@pytest.mark.parametrize(
    ("entity_id", "method", "args"),
    [
        ("button.mantelmount_8436fe_home", "async_recall_preset", (0,)),
        ("button.mantelmount_8436fe_recall_preset_2", "async_recall_preset", (2,)),
        ("button.mantelmount_8436fe_save_preset_3", "async_save_preset", (3,)),
        ("button.mantelmount_8436fe_stop", "async_stop", ()),
        ("button.mantelmount_8436fe_jog_up", "async_jog", (Jog.UP,)),
        ("button.mantelmount_8436fe_jog_left", "async_jog", (Jog.LEFT,)),
    ],
)
async def test_buttons_should_send_command_and_poll_quickly(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock, entity_id: str, method: str, args: tuple
) -> None:
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: entity_id}, blocking=True)

    getattr(mock_client, method).assert_awaited_once_with(*args)
    assert mount.runtime_data.update_interval == MOVING_INTERVAL


async def test_button_should_raise_if_mount_does_not_acknowledge(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.async_recall_preset.side_effect = MantelMountTimeoutError("no reply")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {ATTR_ENTITY_ID: "button.mantelmount_8436fe_home"}, blocking=True
        )


async def test_alps_switch_should_disable_alps(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.async_set_alps_settings.return_value = replace(SETTINGS, enabled=False)

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: "switch.mantelmount_8436fe_alps"}, blocking=True
    )

    mock_client.async_set_alps_settings.assert_awaited_once_with(enabled=False)
    assert hass.states.get("switch.mantelmount_8436fe_alps").state == STATE_OFF


async def test_tv_on_threshold_should_be_written_to_mount(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.async_set_alps_settings.return_value = replace(SETTINGS, tv_on_threshold=300)

    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: "number.mantelmount_8436fe_alps_tv_on_threshold", "value": 300},
        blocking=True,
    )

    mock_client.async_set_alps_settings.assert_awaited_once_with(tv_on_threshold=300)
    assert hass.states.get("number.mantelmount_8436fe_alps_tv_on_threshold").state == "300"


async def test_threshold_should_raise_if_mount_rejects_value(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.async_set_alps_settings.side_effect = ValueError("on threshold must be higher")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: "number.mantelmount_8436fe_alps_tv_off_threshold", "value": 400},
            blocking=True,
        )
    assert hass.states.get("number.mantelmount_8436fe_alps_tv_off_threshold").state == "150"


async def test_smooth_start_should_be_written_to_mount(
    hass: HomeAssistant, mount: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.async_set_alps_settings.return_value = replace(SETTINGS, smooth_start=SmoothStart.MEDIUM)

    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: "select.mantelmount_8436fe_smooth_start", "option": "medium"},
        blocking=True,
    )

    mock_client.async_set_alps_settings.assert_awaited_once_with(smooth_start=SmoothStart.MEDIUM)
    assert hass.states.get("select.mantelmount_8436fe_smooth_start").state == "medium"


async def test_unload_should_succeed(hass: HomeAssistant, mount: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(mount.entry_id)

    assert mount.state is ConfigEntryState.NOT_LOADED
