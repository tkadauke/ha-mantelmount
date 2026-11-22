"""Binary sensors for the MantelMount integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MantelMountConfigEntry, MantelMountCoordinator, MantelMountData
from .entity import MantelMountEntity


@dataclass(frozen=True, kw_only=True)
class MantelMountBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a MantelMount binary sensor."""

    value: Callable[[MantelMountData], bool]


BINARY_SENSORS: tuple[MantelMountBinarySensorDescription, ...] = (
    MantelMountBinarySensorDescription(
        key="tv",
        device_class=BinarySensorDeviceClass.POWER,
        value=lambda data: data.position.tv_on,
    ),
    MantelMountBinarySensorDescription(
        key="moving",
        device_class=BinarySensorDeviceClass.MOVING,
        value=lambda data: data.moving,
    ),
    MantelMountBinarySensorDescription(
        key="home",
        value=lambda data: data.position.is_home,
    ),
    MantelMountBinarySensorDescription(
        key="position_lost",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.status.position_lost,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: MantelMountConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the mount's binary sensors."""
    async_add_entities(MantelMountBinarySensor(entry.runtime_data, description) for description in BINARY_SENSORS)


class MantelMountBinarySensor(MantelMountEntity, BinarySensorEntity):
    """A flag read from the mount."""

    entity_description: MantelMountBinarySensorDescription

    def __init__(self, coordinator: MantelMountCoordinator, description: MantelMountBinarySensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value(self.coordinator.data)
