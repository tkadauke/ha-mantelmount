"""Smooth start select for the MantelMount integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SmoothStart
from .coordinator import MantelMountConfigEntry, MantelMountCoordinator
from .entity import MantelMountEntity, mount_command

OPTIONS = {smooth_start.name.lower(): smooth_start for smooth_start in SmoothStart}


async def async_setup_entry(
    hass: HomeAssistant, entry: MantelMountConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the smooth start select."""
    async_add_entities([SmoothStartSelect(entry.runtime_data)])


class SmoothStartSelect(MantelMountEntity, SelectEntity):
    """How gently the motors ramp up when the mount starts moving."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(OPTIONS)

    def __init__(self, coordinator: MantelMountCoordinator) -> None:
        super().__init__(coordinator, "smooth_start")

    @property
    def current_option(self) -> str:
        return self.coordinator.data.settings.smooth_start.name.lower()

    @mount_command
    async def async_select_option(self, option: str) -> None:
        settings = await self.coordinator.client.async_set_alps_settings(smooth_start=OPTIONS[option])
        await self.coordinator.async_apply_settings(settings)
