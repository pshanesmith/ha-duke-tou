from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow

from .const import CONF_ADDER, CONF_TARIFF, DOMAIN, RATE_OPTIONS, list_tariffs
from .schedule import DEFAULT_TARIFF, TariffError, load_tariff


_LOGGER = logging.getLogger(__name__)


class DukeTouConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        plans = await self.hass.async_add_executor_job(list_tariffs, self.hass)
        if user_input is not None:
            stem = user_input[CONF_TARIFF]
            try:
                tariff = await self.hass.async_add_executor_job(load_tariff, plans[stem])
            except TariffError as err:
                _LOGGER.error("Invalid tariff %s: %s", stem, err)
                errors["base"] = "invalid_tariff"
            else:
                return self.async_create_entry(title=tariff.name, data={CONF_TARIFF: stem})
        default = DEFAULT_TARIFF if DEFAULT_TARIFF in plans else next(iter(plans))
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_TARIFF, default=default): vol.In(sorted(plans))}),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Switch to another rate plan. Rate overrides belong to the old plan, so they reset."""
        entry = self._get_reconfigure_entry()
        plans = await self.hass.async_add_executor_job(list_tariffs, self.hass)
        errors = {}
        if user_input is not None:
            stem = user_input[CONF_TARIFF]
            try:
                tariff = await self.hass.async_add_executor_job(load_tariff, plans[stem])
            except TariffError as err:
                _LOGGER.error("Invalid tariff %s: %s", stem, err)
                errors["base"] = "invalid_tariff"
            else:
                return self.async_update_reload_and_abort(
                    entry, title=tariff.name, data={CONF_TARIFF: stem}, options={}
                )
        current = entry.data.get(CONF_TARIFF, DEFAULT_TARIFF)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_TARIFF, default=current): vol.In(sorted(plans))}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return DukeTouOptionsFlow()


class DukeTouOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        manager = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if manager is None:
            return self.async_abort(reason="not_loaded")
        tariff = manager.tariff
        keys = {tier: RATE_OPTIONS[tier] for tier in tariff.used_tiers}
        current = {key: round(tariff.rates.base(tier) * 100, 5) for tier, key in keys.items()}
        current[CONF_ADDER] = 0.0
        current.update(self.config_entry.options)
        schema = vol.Schema(
            {
                vol.Required(key, default=current[key]): vol.All(
                    vol.Coerce(float), vol.Range(min=0, max=500)
                )
                for key in (*keys.values(), CONF_ADDER)
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
