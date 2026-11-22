"""The MantelMount integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MantelMountClient
from .coordinator import MantelMountConfigEntry, MantelMountCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: MantelMountConfigEntry) -> bool:
    """Set up a MantelMount from a config entry."""
    client = MantelMountClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    coordinator = MantelMountCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MantelMountConfigEntry) -> bool:
    """Unload a MantelMount config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
