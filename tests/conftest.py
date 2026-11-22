"""Shared fixtures for the MantelMount tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mantelmount.api import (
    AlpsSettings,
    DeviceInfo,
    MountPosition,
    MountStatus,
    SmoothStart,
)
from custom_components.mantelmount.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "10.0.0.20"
MAC = "d8:3a:f5:84:36:fe"
STATUS_REPLY = "MMQ0,0,0,0,0,0,33,0,0,693,0,69,1,1,0,4\r"
HOME_POSITION = MountPosition(azimuth=0.0, elevation=0.0, temperature_status="Normal", tv_on=False, tv_current=69)
LOWERED_POSITION = MountPosition(
    azimuth=-2.06, elevation=-98.65, temperature_status="Normal", tv_on=True, tv_current=1070
)
SETTINGS = AlpsSettings(enabled=True, tv_on_threshold=250, tv_off_threshold=150, smooth_start=SmoothStart.NONE)


def fixture_text(name: str) -> str:
    """Return a page captured from a real adapter."""
    return (FIXTURES / name).read_text()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured bedroom mount."""
    return MockConfigEntry(domain=DOMAIN, title="MantelMount 8436fe", unique_id=MAC, data={CONF_HOST: HOST})


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Replace the adapter client in setup and in the config flow with one mock."""
    with (
        patch("custom_components.mantelmount.MantelMountClient", autospec=True) as client_class,
        patch("custom_components.mantelmount.config_flow.MantelMountClient", new=client_class),
    ):
        client = client_class.return_value
        client.base_url = f"http://{HOST}"
        client.async_get_status.return_value = MountStatus.parse(STATUS_REPLY)
        client.async_get_position.return_value = HOME_POSITION
        client.async_get_alps_settings.return_value = SETTINGS
        client.async_get_device_info.return_value = DeviceInfo(mac=MAC, host_name="MantelMount_8436fe")
        client.async_set_alps_settings.return_value = SETTINGS
        yield client
