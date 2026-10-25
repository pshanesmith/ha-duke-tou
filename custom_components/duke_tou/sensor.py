from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .const import DOMAIN, TIER_OPTIONS
from .entity import TouEntity


async def async_setup_entry(hass, entry, async_add_entities):
    m = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            TierSensor(m, entry.entry_id),
            PriceSensor(m, entry.entry_id),
            NextChangeSensor(m, entry.entry_id),
            NextTierSensor(m, entry.entry_id),
        ]
    )


class TierSensor(TouEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = TIER_OPTIONS

    def __init__(self, manager, entry_id):
        super().__init__(manager, entry_id, "tier")

    @property
    def native_value(self):
        return self.manager.tier()

    @property
    def extra_state_attributes(self):
        m = self.manager
        today = m.today()
        attrs = {
            "label": m.tariff.label(m.tier()),
            "season": m.tariff.season(today),
            "holiday": m.tariff.holiday_name(today),
        }
        if m.tariff.has_critical:
            attrs.update(
                critical_days_used_this_year=m.days_used_this_year(),
                critical_days_per_year=m.tariff.critical_days_per_year,
                flagged_critical_days=m.upcoming_critical(),
            )
        return attrs


class PriceSensor(TouEntity, SensorEntity):
    _attr_native_unit_of_measurement = "USD/kWh"
    _attr_suggested_display_precision = 4

    def __init__(self, manager, entry_id):
        super().__init__(manager, entry_id, "price")

    @property
    def native_value(self):
        return round(self.manager.rates.price(self.manager.tier()), 5)

    @property
    def extra_state_attributes(self):
        m = self.manager
        tier = m.tier()
        return {
            "base_price": m.rates.base(tier),
            "adder": m.rates.adder,
            "cents_per_kwh": round(m.rates.price(tier) * 100, 3),
        }


class NextChangeSensor(TouEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, manager, entry_id):
        super().__init__(manager, entry_id, "next_change")

    @property
    def native_value(self):
        nxt = self.manager.next_change()
        return nxt[0] if nxt else None


class NextTierSensor(TouEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = TIER_OPTIONS

    def __init__(self, manager, entry_id):
        super().__init__(manager, entry_id, "next_tier")

    @property
    def native_value(self):
        nxt = self.manager.next_change()
        return nxt[1] if nxt else None

    @property
    def extra_state_attributes(self):
        nxt = self.manager.next_change()
        return {"next_price": self.manager.rates.price(nxt[1])} if nxt else {}
