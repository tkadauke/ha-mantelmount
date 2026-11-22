"""ALPS switch for the MantelMount integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MantelMountConfigEntry, MantelMountCoordinator
from .entity import MantelMountEntity, mount_command


async def async_setup_entry(
    hass: HomeAssistant, entry: MantelMountConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the ALPS switch."""
    async_add_entities([AlpsSwitch(entry.runtime_data)])


class AlpsSwitch(MantelMountEntity, SwitchEntity):
    """Whether the mount lowers and raises itself as the TV turns on and off."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MantelMountCoordinator) -> None:
        super().__init__(coordinator, "alps")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.settings.enabled

    @mount_command
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_apply_settings(await self.coordinator.client.async_set_alps_settings(enabled=True))

    @mount_command
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_apply_settings(
            await self.coordinator.client.async_set_alps_settings(enabled=False)
        )
