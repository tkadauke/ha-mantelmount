"""Polling coordinator for a MantelMount adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AlpsSettings, MantelMountClient, MantelMountError, MountPosition, MountStatus
from .const import (
    COMMAND_FOLLOW_UP,
    DOMAIN,
    IDLE_INTERVAL,
    MOVING_INTERVAL,
    POSITION_TOLERANCE,
    SETTINGS_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type MantelMountConfigEntry = ConfigEntry[MantelMountCoordinator]


@dataclass(frozen=True)
class MantelMountData:
    """One poll's worth of state."""

    status: MountStatus
    position: MountPosition
    settings: AlpsSettings
    moving: bool


class MantelMountCoordinator(DataUpdateCoordinator[MantelMountData]):
    """
    Polls status and position, and the ALPS settings less often.

    The interval drops to :data:`MOVING_INTERVAL` while the position changes and for
    :data:`COMMAND_FOLLOW_UP` after a command, so movement is tracked closely without
    hammering the adapter while it sits still.
    """

    config_entry: MantelMountConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MantelMountConfigEntry, client: MantelMountClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=IDLE_INTERVAL)
        self.client = client
        self._settings: AlpsSettings | None = None
        self._settings_read_at: datetime | None = None
        self._follow_up_until: datetime | None = None

    async def _async_update_data(self) -> MantelMountData:
        try:
            status = await self.client.async_get_status()
            position = await self.client.async_get_position()
            settings = await self._async_settings()
        except MantelMountError as err:
            raise UpdateFailed(str(err)) from err
        moving = self.data is not None and (
            abs(position.azimuth - self.data.position.azimuth) > POSITION_TOLERANCE
            or abs(position.elevation - self.data.position.elevation) > POSITION_TOLERANCE
        )
        following_up = self._follow_up_until is not None and dt_util.utcnow() < self._follow_up_until
        self.update_interval = MOVING_INTERVAL if moving or following_up else IDLE_INTERVAL
        return MantelMountData(status=status, position=position, settings=settings, moving=moving)

    async def _async_settings(self) -> AlpsSettings:
        now = dt_util.utcnow()
        if (
            self._settings is None
            or self._settings_read_at is None
            or now - self._settings_read_at >= SETTINGS_INTERVAL
        ):
            self._settings = await self.client.async_get_alps_settings()
            self._settings_read_at = now
        return self._settings

    async def async_after_command(self) -> None:
        """Poll quickly for a while so the movement a command started shows up promptly."""
        self._follow_up_until = dt_util.utcnow() + COMMAND_FOLLOW_UP
        self.update_interval = MOVING_INTERVAL
        await self.async_request_refresh()

    async def async_apply_settings(self, settings: AlpsSettings) -> None:
        """Publish settings the adapter just confirmed without waiting for the next settings read."""
        self._settings = settings
        self._settings_read_at = dt_util.utcnow()
        if self.data is not None:
            self.async_set_updated_data(
                MantelMountData(
                    status=self.data.status, position=self.data.position, settings=settings, moving=self.data.moving
                )
            )
