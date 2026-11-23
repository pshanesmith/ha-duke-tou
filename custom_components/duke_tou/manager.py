"""Shared state: the critical peak days you flagged, and the current tier."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import schedule
from .const import DOMAIN, SHIFT_OPTIONS, SIGNAL_UPDATE, STORAGE_VERSION


class TouManager:
    def __init__(self, hass: HomeAssistant, tariff: schedule.Tariff, rates: schedule.Rates) -> None:
        self.hass = hass
        self.tariff = tariff
        self.rates = rates
        self._store = Store(hass, STORAGE_VERSION, DOMAIN)
        self.critical_days: dict[date, int] = {}
        self.shift_choice = "standard"  # applied when the switches flag a day

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.shift_choice = data.get("shift_choice", "standard")
        self.critical_days = {
            date.fromisoformat(k): int(v) for k, v in data.get("critical_days", {}).items()
        }
        self._prune()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "shift_choice": self.shift_choice,
                "critical_days": {d.isoformat(): v for d, v in self.critical_days.items()},
            }
        )

    def _prune(self) -> None:
        """Keep the current and previous calendar year for the yearly count."""
        year = self.now().year
        self.critical_days = {d: v for d, v in self.critical_days.items() if d.year >= year - 1}

    @staticmethod
    def now() -> datetime:
        return dt_util.now()  # local time in the Home Assistant time zone

    @property
    def shift_hours(self) -> int:
        return SHIFT_OPTIONS[self.shift_choice]

    def today(self) -> date:
        return self.now().date()

    def is_flagged(self, d: date) -> bool:
        return d in self.critical_days

    def days_used_this_year(self) -> int:
        year = self.now().year
        return sum(1 for d in self.critical_days if d.year == year)

    def tier(self) -> str:
        return self.tariff.tier_at(self.now(), self.critical_days)

    def next_change(self) -> tuple[datetime, str] | None:
        return self.tariff.next_change(self.now(), self.critical_days)

    def next_peak_start(self) -> datetime | None:
        return self.tariff.next_peak_start(self.now(), self.critical_days)

    def upcoming_critical(self) -> list[str]:
        today = self.today()
        return sorted(d.isoformat() for d in self.critical_days if d >= today)

    @callback
    def notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def async_set_critical(self, d: date, shift: int | None = None) -> None:
        shift = self.shift_hours if shift is None else shift
        if abs(shift) > self.tariff.max_shift_hours:
            raise ServiceValidationError(f"shift must be within +/-{self.tariff.max_shift_hours} hours")
        self.critical_days[d] = shift
        await self._async_save()
        self.notify()

    async def async_clear_critical(self, d: date) -> None:
        self.critical_days.pop(d, None)
        await self._async_save()
        self.notify()

    async def async_set_shift_choice(self, choice: str) -> None:
        """Changing the shift also re-times a day that is already flagged for
        today or tomorrow, so you can correct it after the fact."""
        self.shift_choice = choice
        today = self.today()
        for d in (today, today + timedelta(days=1)):
            if d in self.critical_days:
                self.critical_days[d] = self.shift_hours
        await self._async_save()
        self.notify()
