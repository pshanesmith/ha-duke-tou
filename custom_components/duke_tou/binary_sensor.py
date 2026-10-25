from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN
from .entity import TouEntity
from .schedule import CRITICAL_PEAK, format_ranges


async def async_setup_entry(hass, entry, async_add_entities):
    m = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CriticalActive(m, entry.entry_id), CriticalFlagged(m, entry.entry_id)])


class CriticalActive(TouEntity, BinarySensorEntity):
    """On while the current hour is billed at the critical peak rate."""

    def __init__(self, manager, entry_id):
        super().__init__(manager, entry_id, "critical_peak_active")

    @property
    def is_on(self):
        return self.manager.tier() == CRITICAL_PEAK


class CriticalFlagged(TouEntity, BinarySensorEntity):
    """On when today or tomorrow is flagged as a critical peak day.

    Handy for a "reduce usage" automation or a display warning that should
    show before the window starts.
    """

    def __init__(self, manager, entry_id):
        super().__init__(manager, entry_id, "critical_peak_flagged")

    @property
    def is_on(self):
        today = self.manager.today()
        return self.manager.is_flagged(today) or self.manager.is_flagged(today + timedelta(days=1))

    @property
    def extra_state_attributes(self):
        m = self.manager
        today = m.today()
        out = {}
        for label, d in (("today", today), ("tomorrow", today + timedelta(days=1))):
            if m.is_flagged(d):
                out[label] = format_ranges(m.tariff.critical_window(d, m.critical_days[d]))
        return out
