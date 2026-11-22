"""ALPS threshold numbers for the MantelMount integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import AlpsSettings, MantelMountClient
from .coordinator import MantelMountConfigEntry, MantelMountCoordinator
from .entity import MantelMountEntity, mount_command


@dataclass(frozen=True, kw_only=True)
class AlpsThresholdDescription(NumberEntityDescription):
    """Describes one of the TV current thresholds ALPS switches at."""

    value: Callable[[AlpsSettings], int]
    apply: Callable[[MantelMountClient, int], Awaitable[AlpsSettings]]


THRESHOLDS: tuple[AlpsThresholdDescription, ...] = (
    AlpsThresholdDescription(
        key="tv_on_threshold",
        native_min_value=20,
        native_max_value=5000,
        value=lambda settings: settings.tv_on_threshold,
        apply=lambda client, value: client.async_set_alps_settings(tv_on_threshold=value),
    ),
    AlpsThresholdDescription(
        key="tv_off_threshold",
        native_min_value=10,
        native_max_value=5000,
        value=lambda settings: settings.tv_off_threshold,
        apply=lambda client, value: client.async_set_alps_settings(tv_off_threshold=value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: MantelMountConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the ALPS threshold numbers."""
    async_add_entities(AlpsThreshold(entry.runtime_data, description) for description in THRESHOLDS)


class AlpsThreshold(MantelMountEntity, NumberEntity):
    """A TV current threshold; the on threshold must stay above the off threshold."""

    entity_description: AlpsThresholdDescription
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.MILLIAMPERE
    _attr_native_step = 10
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: MantelMountCoordinator, description: AlpsThresholdDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int:
        return self.entity_description.value(self.coordinator.data.settings)

    @mount_command
    async def async_set_native_value(self, value: float) -> None:
        settings = await self.entity_description.apply(self.coordinator.client, round(value))
        await self.coordinator.async_apply_settings(settings)
