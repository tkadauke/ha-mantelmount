"""Diagnostics for the MantelMount integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import MantelMountConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: MantelMountConfigEntry) -> dict[str, Any]:
    """Return the entry and the last polled state."""
    data = entry.runtime_data.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "status": asdict(data.status),
        "position": asdict(data.position),
        "settings": asdict(data.settings),
        "moving": data.moving,
    }
