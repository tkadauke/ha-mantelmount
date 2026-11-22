"""Buttons for the MantelMount integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import PRESET_COUNT, Jog, MantelMountClient
from .coordinator import MantelMountConfigEntry, MantelMountCoordinator
from .entity import MantelMountEntity, mount_command


@dataclass(frozen=True, kw_only=True)
class MantelMountButtonDescription(ButtonEntityDescription):
    """Describes a button that sends one command to the mount."""

    press: Callable[[MantelMountClient], Awaitable[None]]


def preset_buttons(preset: int) -> tuple[MantelMountButtonDescription, ...]:
    """Recall and save buttons for one preset slot."""
    return (
        MantelMountButtonDescription(
            key=f"recall_preset_{preset}",
            translation_placeholders={"preset": str(preset)},
            press=lambda client: client.async_recall_preset(preset),
        ),
        MantelMountButtonDescription(
            key=f"save_preset_{preset}",
            translation_placeholders={"preset": str(preset)},
            entity_category=EntityCategory.CONFIG,
            press=lambda client: client.async_save_preset(preset),
        ),
    )


BUTTONS: tuple[MantelMountButtonDescription, ...] = (
    MantelMountButtonDescription(key="home", press=lambda client: client.async_recall_preset(0)),
    MantelMountButtonDescription(key="stop", press=lambda client: client.async_stop()),
    MantelMountButtonDescription(key="jog_up", press=lambda client: client.async_jog(Jog.UP)),
    MantelMountButtonDescription(key="jog_down", press=lambda client: client.async_jog(Jog.DOWN)),
    MantelMountButtonDescription(key="jog_left", press=lambda client: client.async_jog(Jog.LEFT)),
    MantelMountButtonDescription(key="jog_right", press=lambda client: client.async_jog(Jog.RIGHT)),
    *(button for preset in range(1, PRESET_COUNT + 1) for button in preset_buttons(preset)),
)

TRANSLATED_KEYS = {"recall_preset", "save_preset"}


async def async_setup_entry(
    hass: HomeAssistant, entry: MantelMountConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the mount's command buttons."""
    async_add_entities(MantelMountButton(entry.runtime_data, description) for description in BUTTONS)


class MantelMountButton(MantelMountEntity, ButtonEntity):
    """Sends a command and then polls quickly to follow the movement."""

    entity_description: MantelMountButtonDescription

    def __init__(self, coordinator: MantelMountCoordinator, description: MantelMountButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        family = description.key.rsplit("_", 1)[0]
        if family in TRANSLATED_KEYS:
            self._attr_translation_key = family

    @mount_command
    async def async_press(self) -> None:
        await self.entity_description.press(self.coordinator.client)
        await self.coordinator.async_after_command()
