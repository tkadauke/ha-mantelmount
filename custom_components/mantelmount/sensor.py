"""Sensors for the MantelMount integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import DEGREE, EntityCategory, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MantelMountConfigEntry, MantelMountCoordinator, MantelMountData
from .entity import MantelMountEntity


@dataclass(frozen=True, kw_only=True)
class MantelMountSensorDescription(SensorEntityDescription):
    """Describes a MantelMount sensor."""

    value: Callable[[MantelMountData], float | int | str]


SENSORS: tuple[MantelMountSensorDescription, ...] = (
    MantelMountSensorDescription(
        key="elevation",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value=lambda data: data.position.elevation,
    ),
    MantelMountSensorDescription(
        key="azimuth",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value=lambda data: data.position.azimuth,
    ),
    MantelMountSensorDescription(
        key="tv_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.position.tv_current,
    ),
    MantelMountSensorDescription(
        key="temperature_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.position.temperature_status,
    ),
    MantelMountSensorDescription(
        key="temperature_reading",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value=lambda data: data.status.temperature,
    ),
    MantelMountSensorDescription(
        key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.status.error_code,
    ),
    MantelMountSensorDescription(
        key="last_preset",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.status.last_preset,
    ),
    MantelMountSensorDescription(
        key="last_event_source",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda data: data.status.last_event_source,
    ),
    MantelMountSensorDescription(
        key="left_actuator",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda data: data.status.left_actuator,
    ),
    MantelMountSensorDescription(
        key="right_actuator",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda data: data.status.right_actuator,
    ),
    MantelMountSensorDescription(
        key="left_motor_current",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value=lambda data: data.status.left_motor_current,
    ),
    MantelMountSensorDescription(
        key="right_motor_current",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value=lambda data: data.status.right_motor_current,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: MantelMountConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the mount's sensors."""
    async_add_entities(MantelMountSensor(entry.runtime_data, description) for description in SENSORS)


class MantelMountSensor(MantelMountEntity, SensorEntity):
    """A value read from the mount."""

    entity_description: MantelMountSensorDescription

    def __init__(self, coordinator: MantelMountCoordinator, description: MantelMountSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str:
        return self.entity_description.value(self.coordinator.data)
