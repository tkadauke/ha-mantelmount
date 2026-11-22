"""Config flow for the MantelMount integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import voluptuous as vol

from .api import DeviceInfo, MantelMountClient, MantelMountError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class MantelMountConfigFlow(ConfigFlow, domain=DOMAIN):
    """Adds a MantelMount by host, or by DHCP discovery of its ``MantelMount_*`` host name."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._name: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the adapter's host and check that it answers."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            info = await self._async_probe(host)
            if info is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(format_mac(info.mac))
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(title=self._title(info), data={CONF_HOST: host})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Handle a DHCP lease, updating the host of an already configured mount."""
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        info = await self._async_probe(discovery_info.ip)
        if info is None:
            return self.async_abort(reason="cannot_connect")
        self._host = discovery_info.ip
        self._name = self._title(info)
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm adding a discovered mount."""
        assert self._host is not None and self._name is not None
        if user_input is not None:
            return self.async_create_entry(title=self._name, data={CONF_HOST: self._host})
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm", description_placeholders={"name": self._name, "host": self._host}
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Point an existing entry at a new host, refusing a different mount."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            info = await self._async_probe(host)
            if info is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(format_mac(info.mac))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: host})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input or dict(entry.data)),
            errors=errors,
        )

    async def _async_probe(self, host: str) -> DeviceInfo | None:
        client = MantelMountClient(host, async_get_clientsession(self.hass))
        try:
            await client.async_get_status()
            return await client.async_get_device_info()
        except MantelMountError as err:
            _LOGGER.debug("MantelMount at %s did not answer: %s", host, err)
            return None

    @staticmethod
    def _title(info: DeviceInfo) -> str:
        return info.host_name.replace("_", " ") if info.host_name else "MantelMount"
