from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import DOMAIN, SHIFT_OPTIONS
from .entity import TouEntity


async def async_setup_entry(hass, entry, async_add_entities):
    m = hass.data[DOMAIN][entry.entry_id]
    if not m.tariff.has_critical:
        return
    async_add_entities([ShiftSelect(m, entry.entry_id)])


class ShiftSelect(TouEntity, SelectEntity):
    """Whether Duke moved the critical window an hour earlier or later."""

    _attr_options = list(SHIFT_OPTIONS)

    def __init__(self, manager, entry_id):
        super().__init__(manager, entry_id, "critical_peak_shift")

    @property
    def current_option(self):
        return self.manager.shift_choice

    async def async_select_option(self, option: str) -> None:
        await self.manager.async_set_shift_choice(option)
