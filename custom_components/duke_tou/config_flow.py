from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow

from .const import CONF_ADDER, DOMAIN, RATE_OPTIONS, tariff_path
from .schedule import load_tariff


class DukeTouConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Duke Energy R-TOU-CPP", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    def async_get_options_flow(config_entry):
        return DukeTouOptionsFlow()


class DukeTouOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        tariff = await self.hass.async_add_executor_job(load_tariff, tariff_path(self.hass))
        current = {key: round(tariff.rates.base(tier) * 100, 5) for tier, key in RATE_OPTIONS.items()}
        current[CONF_ADDER] = 0.0
        current.update(self.config_entry.options)
        schema = vol.Schema(
            {
                vol.Required(key, default=current[key]): vol.All(
                    vol.Coerce(float), vol.Range(min=0, max=500)
                )
                for key in (*RATE_OPTIONS.values(), CONF_ADDER)
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
