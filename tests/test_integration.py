"""Integration tests; run with pytest-homeassistant-custom-component (see README)."""
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

import shutil
from pathlib import Path

import pytest

DOMAIN = "duke_tou"


@pytest.fixture(autouse=True)
def clean_custom_plans(hass):
    """The test config directory is shared, so remove plan files tests drop there."""
    shutil.rmtree(Path(hass.config.path(DOMAIN)), ignore_errors=True)
    yield
    shutil.rmtree(Path(hass.config.path(DOMAIN)), ignore_errors=True)


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


def _write_custom_tariff(hass, text, name="duke_progress_nc_r_tou_cpp.toml"):
    from pathlib import Path

    path = Path(hass.config.path("duke_tou", name))
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


# --- rate plan selection ---------------------------------------------------------


async def _setup_plan(hass, stem):
    await hass.config.async_set_time_zone("America/New_York")
    entry = MockConfigEntry(domain=DOMAIN, data={"tariff": stem})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _ids(hass, domain):
    return [s.entity_id for s in hass.states.async_all(domain) if "duke" in s.entity_id]


async def test_plan_without_critical_peak_has_no_override_entities(hass, freezer):
    freezer.move_to("2026-10-26 11:30:00-04:00")
    await _setup_plan(hass, "duke_progress_nc_r_tou")
    assert hass.states.get("sensor.duke_energy_r_tou_tier").state == "discount"
    assert float(hass.states.get("sensor.duke_energy_r_tou_price").state) == 0.07372
    assert _ids(hass, "switch") == [] and _ids(hass, "select") == []
    assert _ids(hass, "binary_sensor") == []
    assert not hass.services.has_service(DOMAIN, "set_critical_peak")


async def test_ev_plan_uses_standard_label_and_wraps_midnight(hass, freezer):
    freezer.move_to("2026-10-26 23:30:00-04:00")
    await _setup_plan(hass, "duke_progress_nc_r_tou_ev")
    tier = hass.states.get("sensor.duke_energy_r_tou_ev_tier")
    assert tier.state == "discount"
    freezer.move_to("2026-10-27 05:00:30-04:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    tier = hass.states.get("sensor.duke_energy_r_tou_ev_tier")
    assert tier.state == "off_peak" and tier.attributes["label"] == "Standard"
    assert float(hass.states.get("sensor.duke_energy_r_tou_ev_price").state) == 0.13096


async def test_options_only_list_tiers_the_plan_uses(hass, freezer):
    freezer.move_to("2026-10-26 11:30:00-04:00")
    entry = await _setup_plan(hass, "duke_progress_nc_r_tou_ev")
    result = await hass.config_entries.options.async_init(entry.entry_id)
    keys = {str(k) for k in result["data_schema"].schema}
    assert keys == {"off_peak_cents", "discount_cents", "adder_cents"}


async def test_config_flow_lists_all_plans_and_creates_entry(hass):
    from homeassistant.data_entry_flow import FlowResultType

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    options = list(result["data_schema"].schema["tariff"].container)
    assert options == [
        "duke_progress_nc_r_tou",
        "duke_progress_nc_r_tou_cpp",
        "duke_progress_nc_r_tou_ev",
        "duke_progress_nc_r_toud",
    ]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tariff": "duke_progress_nc_r_toud"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Duke Energy R-TOUD"
    assert result["data"] == {"tariff": "duke_progress_nc_r_toud"}


async def test_reconfigure_switches_plan_and_resets_overrides(hass, freezer):
    freezer.move_to("2026-10-26 11:30:00-04:00")
    entry = await _setup_plan(hass, "duke_progress_nc_r_tou_cpp")
    hass.config_entries.async_update_entry(entry, options={"discount_cents": 1.0})
    await hass.async_block_till_done()
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tariff": "duke_progress_nc_r_tou_ev"}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {"tariff": "duke_progress_nc_r_tou_ev"} and entry.options == {}
    # Entity ids stay as first created, so dashboards survive a plan change.
    assert float(hass.states.get("sensor.duke_energy_r_tou_cpp_price").state) == 0.13096
    assert hass.states.get("switch.duke_energy_r_tou_cpp_critical_peak_today") is None


async def test_custom_plan_file_is_offered(hass):
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.duke_tou.schedule import TARIFF_DIR

    _write_custom_tariff(
        hass, (TARIFF_DIR / "duke_progress_nc_r_tou_ev.toml").read_text(), "my_plan.toml"
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert "my_plan" in list(result["data_schema"].schema["tariff"].container)
