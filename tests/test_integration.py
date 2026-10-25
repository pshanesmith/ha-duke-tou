"""Integration tests; run with pytest-homeassistant-custom-component (see README)."""
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

DOMAIN = "duke_tou"


async def _setup(hass):
    await hass.config.async_set_time_zone("America/New_York")
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


_DOMAINS = {"tier": "sensor", "price": "sensor", "next_tier": "sensor", "next_change": "sensor",
            "critical_peak_active": "binary_sensor", "critical_peak_today_or_tomorrow": "binary_sensor",
            "critical_peak_today": "switch", "critical_peak_window": "select"}


def _state(hass, suffix):
    name = suffix.lstrip("_")
    state = hass.states.get(f"{_DOMAINS[name]}.duke_energy_r_tou_cpp_{name}")
    assert state is not None, [s.entity_id for s in hass.states.async_all()]
    return state


async def test_tier_and_price(hass, freezer: FrozenDateTimeFactory):
    freezer.move_to("2026-10-26 11:30:00-04:00")  # Monday, winter, discount
    await _setup(hass)
    assert _state(hass, "_tier").state == "discount"
    assert float(_state(hass, "_price").state) == 0.08274
    assert _state(hass, "_next_tier").state == "off_peak"


async def test_critical_peak_override_and_hourly_tick(hass, freezer: FrozenDateTimeFactory):
    freezer.move_to("2026-10-26 05:59:30-04:00")
    await _setup(hass)
    assert _state(hass, "_tier").state == "off_peak"
    await hass.services.async_call(
        DOMAIN, "set_critical_peak", {"date": "2026-10-26"}, blocking=True
    )
    assert _state(hass, "_critical_peak_today_or_tomorrow").state == "on"
    assert _state(hass, "_critical_peak_today").state == "on"

    freezer.tick(timedelta(seconds=40))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, "_tier").state == "critical_peak"
    assert float(_state(hass, "_price").state) == 0.41002
    assert _state(hass, "_critical_peak_active").state == "on"

    await hass.services.async_call(
        DOMAIN, "clear_critical_peak", {"date": "2026-10-26"}, blocking=True
    )
    assert _state(hass, "_tier").state == "on_peak"


async def test_switch_and_shift(hass, freezer: FrozenDateTimeFactory):
    freezer.move_to("2026-07-15 16:00:00-04:00")
    await _setup(hass)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": _state(hass, "_critical_peak_window").entity_id, "option": "earlier"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": _state(hass, "_critical_peak_today").entity_id},
        blocking=True,
    )
    freezer.move_to("2026-07-15 17:30:00-04:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, "_tier").state == "critical_peak"


async def test_options_change_rates(hass, freezer: FrozenDateTimeFactory):
    freezer.move_to("2026-10-26 11:30:00-04:00")
    entry = await _setup(hass)
    hass.config_entries.async_update_entry(entry, options={"discount_cents": 8.274, "adder_cents": 2.0})
    await hass.async_block_till_done()
    assert abs(float(_state(hass, "_price").state) - 0.10274) < 1e-6


def _write_custom_tariff(hass, text):
    from pathlib import Path

    path = Path(hass.config.path("duke_tou", "tariff.toml"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


async def test_config_dir_tariff_overrides_bundled(hass, freezer: FrozenDateTimeFactory):
    from custom_components.duke_tou.schedule import BUNDLED_TARIFF

    text = BUNDLED_TARIFF.read_text().replace("discount = 8.274", "discount = 5.0")
    _write_custom_tariff(hass, text)
    freezer.move_to("2026-10-26 11:30:00-04:00")
    await _setup(hass)
    assert float(_state(hass, "_price").state) == 0.05


async def test_invalid_tariff_fails_setup(hass, freezer: FrozenDateTimeFactory):
    from homeassistant.config_entries import ConfigEntryState

    _write_custom_tariff(hass, "name = 'broken'\n")
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
