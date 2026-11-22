"""Base entity for the MantelMount integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, Concatenate

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import MantelMountError
from .const import DOMAIN, MANUFACTURER
from .coordinator import MantelMountCoordinator


class MantelMountEntity(CoordinatorEntity[MantelMountCoordinator]):
    """An entity attached to the mount's device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MantelMountCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        assert entry.unique_id is not None
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            connections={(CONNECTION_NETWORK_MAC, entry.unique_id)},
            manufacturer=MANUFACTURER,
            name=entry.title,
            sw_version=str(coordinator.data.status.firmware_version),
            configuration_url=coordinator.client.base_url,
        )


def mount_command[EntityT: MantelMountEntity, **P](
    func: Callable[Concatenate[EntityT, P], Awaitable[Any]],
) -> Callable[Concatenate[EntityT, P], Awaitable[None]]:
    """
    Turn adapter errors into :class:`HomeAssistantError` so they reach the caller.

    Invalid values (:class:`ValueError`) are reported the same way with the reason.
    """

    @wraps(func)
    async def wrapper(self: EntityT, *args: P.args, **kwargs: P.kwargs) -> None:
        try:
            await func(self, *args, **kwargs)
        except MantelMountError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        except ValueError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_value", translation_placeholders={"error": str(err)}
            ) from err

    return wrapper
