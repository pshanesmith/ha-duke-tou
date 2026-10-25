from __future__ import annotations

from datetime import timedelta

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .entity import TouEntity


async def async_setup_entry(hass, entry, async_add_entities):
    m = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            CriticalDaySwitch(m, entry.entry_id, "critical_peak_today", 0),
            CriticalDaySwitch(m, entry.entry_id, "critical_peak_tomorrow", 1),
        ]
    )


class CriticalDaySwitch(TouEntity, SwitchEntity):
    """Flag a day as a critical peak day, using the selected window shift."""

    def __init__(self, manager, entry_id, key, offset_days):
        super().__init__(manager, entry_id, key)
        self._offset = offset_days

    def _day(self):
        # Computed live so "tomorrow" rolls forward at midnight.
        return self.manager.today() + timedelta(days=self._offset)

    @property
    def is_on(self):
        return self.manager.is_flagged(self._day())

    async def async_turn_on(self, **kwargs):
        await self.manager.async_set_critical(self._day())

    async def async_turn_off(self, **kwargs):
        await self.manager.async_clear_critical(self._day())
