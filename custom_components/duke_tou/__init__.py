"""Time-of-use tariff (Duke Energy Progress NC R-TOU-CPP): tier, price, critical peak override."""
from __future__ import annotations


import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_CLEAR_CRITICAL,
    SERVICE_SET_CRITICAL,
    rates_from_options,
    tariff_path,
)
from .manager import TouManager
from .schedule import TariffError, load_tariff


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        tariff = await hass.async_add_executor_job(load_tariff, tariff_path(hass))
    except TariffError as err:
        raise ConfigEntryError(f"Invalid tariff: {err}") from err
    manager = TouManager(hass, tariff, rates_from_options(tariff, dict(entry.options)))
    await manager.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager

    @callback
    def _tick(_now) -> None:
        manager.notify()

    # Every tariff boundary is on the hour; tick just after it.
    entry.async_on_unload(async_track_time_change(hass, _tick, minute=0, second=1))
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    def _manager() -> TouManager:
        return hass.data[DOMAIN][entry.entry_id]

    async def set_critical(call: ServiceCall) -> None:
        shift = call.data.get("shift_hours")
        await _manager().async_set_critical(call.data["date"], shift)

    async def clear_critical(call: ServiceCall) -> None:
        await _manager().async_clear_critical(call.data["date"])

    if not hass.services.has_service(DOMAIN, SERVICE_SET_CRITICAL):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_CRITICAL,
            set_critical,
            schema=vol.Schema(
                {
                    vol.Required("date"): cv.date,
                    vol.Optional("shift_hours"): vol.All(vol.Coerce(int), vol.Range(min=-12, max=12)),
                }
            ),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_CRITICAL,
            clear_critical,
            schema=vol.Schema({vol.Required("date"): cv.date}),
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_CRITICAL)
            hass.services.async_remove(DOMAIN, SERVICE_CLEAR_CRITICAL)
    return ok
