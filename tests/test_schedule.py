"""Tests for the Home Assistant Duke R-TOU-CPP tariff engine (no HA needed)."""
import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_path = Path(__file__).parent.parent / "custom_components/duke_tou/schedule.py"
_spec = importlib.util.spec_from_file_location("duke_tou_schedule", _path)
s = importlib.util.module_from_spec(_spec)
sys.modules["duke_tou_schedule"] = s
_spec.loader.exec_module(s)

ET = ZoneInfo("America/New_York")
T = s.load_tariff(s.BUNDLED_TARIFF)


def at(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=ET)


def test_easter_and_good_friday():
    assert s.easter(2026) == date(2026, 4, 5)
    assert s.easter(2027) == date(2027, 3, 28)
    assert T.holiday_name(date(2026, 4, 3)) == "Good Friday"


def test_2026_holidays():
    h = T.holiday_dates(2026)
    assert date(2026, 1, 1) in h  # Thursday
    assert date(2026, 5, 25) in h  # Memorial Day
    assert date(2026, 7, 3) in h  # July 4 is a Saturday -> Friday before
    assert date(2026, 7, 4) not in h
    assert date(2026, 9, 7) in h  # Labor Day
    assert date(2026, 11, 26) in h and date(2026, 11, 27) in h
    assert date(2026, 12, 25) in h


def test_sunday_holiday_moves_to_monday():
    # Christmas 2022 was a Sunday
    assert T.is_holiday(date(2022, 12, 26))
    assert not T.is_holiday(date(2022, 12, 25))


def test_new_years_saturday_observed_prior_dec_31():
    # Jan 1 2028 is a Saturday -> Friday Dec 31 2027
    assert T.is_holiday(date(2027, 12, 31))
    assert not T.is_holiday(date(2028, 1, 1))


def test_summer_weekday_tiers():
    d = (2026, 7, 15)  # Wednesday
    assert T.tier_at(at(*d, 0)) == s.OFF_PEAK
    assert T.tier_at(at(*d, 1)) == s.DISCOUNT
    assert T.tier_at(at(*d, 5, 59)) == s.DISCOUNT
    assert T.tier_at(at(*d, 6)) == s.OFF_PEAK
    assert T.tier_at(at(*d, 12)) == s.OFF_PEAK  # no midday discount in summer
    assert T.tier_at(at(*d, 17, 59)) == s.OFF_PEAK
    assert T.tier_at(at(*d, 18)) == s.ON_PEAK
    assert T.tier_at(at(*d, 20, 59)) == s.ON_PEAK
    assert T.tier_at(at(*d, 21)) == s.OFF_PEAK


def test_non_summer_weekday_tiers():
    d = (2026, 10, 26)  # Monday
    assert T.tier_at(at(*d, 1)) == s.DISCOUNT
    assert T.tier_at(at(*d, 3)) == s.OFF_PEAK
    assert T.tier_at(at(*d, 6)) == s.ON_PEAK
    assert T.tier_at(at(*d, 9)) == s.OFF_PEAK
    assert T.tier_at(at(*d, 11)) == s.DISCOUNT
    assert T.tier_at(at(*d, 15, 59)) == s.DISCOUNT
    assert T.tier_at(at(*d, 16)) == s.OFF_PEAK
    assert T.tier_at(at(*d, 18)) == s.OFF_PEAK  # evening is not peak in winter


def test_weekend_and_holiday_have_no_on_peak():
    assert T.tier_at(at(2026, 10, 24, 7)) == s.OFF_PEAK  # Saturday
    assert T.tier_at(at(2026, 10, 25, 7)) == s.OFF_PEAK  # Sunday
    assert T.tier_at(at(2026, 11, 26, 7)) == s.OFF_PEAK  # Thanksgiving
    assert T.tier_at(at(2026, 7, 3, 19)) == s.OFF_PEAK  # observed July 4
    # discount still applies on holidays
    assert T.tier_at(at(2026, 11, 26, 12)) == s.DISCOUNT


def test_month_boundaries():
    assert T.season(date(2026, 5, 1)) == T.season(date(2026, 9, 30)) == "summer"
    assert T.season(date(2026, 4, 30)) == T.season(date(2026, 10, 1)) == "non_summer"


def test_critical_peak_replaces_on_peak_window():
    crit = {date(2026, 7, 15): 0}
    assert T.tier_at(at(2026, 7, 15, 17), crit) == s.OFF_PEAK
    assert T.tier_at(at(2026, 7, 15, 18), crit) == s.CRITICAL_PEAK
    assert T.tier_at(at(2026, 7, 15, 21), crit) == s.OFF_PEAK
    assert T.tier_at(at(2026, 7, 16, 19), crit) == s.ON_PEAK  # other days unaffected


def test_critical_peak_shift():
    early = {date(2026, 7, 15): -1}
    assert T.tier_at(at(2026, 7, 15, 17), early) == s.CRITICAL_PEAK
    assert T.tier_at(at(2026, 7, 15, 19, 59), early) == s.CRITICAL_PEAK
    assert T.tier_at(at(2026, 7, 15, 20), early) == s.ON_PEAK  # shifted-out hour reverts
    late = {date(2026, 1, 14): 1}  # winter 7-10 am
    assert T.tier_at(at(2026, 1, 14, 6), late) == s.ON_PEAK  # shifted-out hour reverts
    assert T.tier_at(at(2026, 1, 14, 9), late) == s.CRITICAL_PEAK
    assert T.tier_at(at(2026, 1, 14, 10), late) == s.OFF_PEAK


def test_critical_peak_on_flagged_weekend_is_honoured():
    assert T.tier_at(at(2026, 10, 24, 7), {date(2026, 10, 24): 0}) == s.CRITICAL_PEAK


def test_next_change():
    t, tier = T.next_change(at(2026, 10, 26, 5, 30))
    assert (t.hour, tier) == (6, s.ON_PEAK)
    t, tier = T.next_change(at(2026, 10, 26, 7))
    assert (t.hour, tier) == (9, s.OFF_PEAK)
    t, tier = T.next_change(at(2026, 10, 26, 7), {date(2026, 10, 26): 0})
    assert (t.hour, tier) == (9, s.OFF_PEAK)
    t, tier = T.next_change(at(2026, 10, 26, 5, 30), {date(2026, 10, 26): 0})
    assert (t.hour, tier) == (6, s.CRITICAL_PEAK)


def test_next_change_across_midnight():
    t, tier = T.next_change(at(2026, 7, 15, 22))
    assert (t.day, t.hour, tier) == (16, 1, s.DISCOUNT)


def test_dst_transition():
    # Fall back Nov 1 2026: 01:00 EDT repeats. Never raises, always moves forward.
    now = at(2026, 11, 1, 0, 30)
    t, tier = T.next_change(now)
    assert t > now and tier == s.DISCOUNT
    # Spring forward Mar 8 2026
    t, _ = T.next_change(at(2026, 3, 8, 0, 30))
    assert t > at(2026, 3, 8, 0, 30)


def test_prices():
    assert T.rates.base(s.ON_PEAK) == 0.21952
    assert T.rates.base(s.DISCOUNT) == 0.08274
    r = s.Rates(**{**T.rates.__dict__, "adder": 0.03})
    assert abs(r.price(s.CRITICAL_PEAK) - 0.44002) < 1e-9


def test_critical_window_text():
    assert s.format_ranges(T.critical_window(date(2026, 1, 14), 1)) == "07:00-10:00"
    assert T.critical_days_per_year == 20 and T.max_shift_hours == 1


# --- the tariff really is data ---------------------------------------------------

import copy
import tomllib

import pytest

RAW = tomllib.loads(s.BUNDLED_TARIFF.read_text())


def mutated(**changes):
    raw = copy.deepcopy(RAW)
    for key, value in changes.items():
        raw[key] = value
    return raw


def test_different_tariff_changes_behaviour():
    raw = mutated()
    raw["periods"][0]["hours"] = {"summer": [[14, 19]], "non_summer": [[17, 20]]}
    raw["holidays"]["rules"] = [{"name": "Groundhog Day", "month": 2, "day": 2}]
    raw["seasons"] = {"summer": [6, 7, 8], "non_summer": [1, 2, 3, 4, 5, 9, 10, 11, 12]}
    t = s.parse_tariff(raw)
    assert t.tier_at(at(2026, 7, 15, 15)) == s.ON_PEAK
    assert t.tier_at(at(2026, 5, 13, 18)) == s.ON_PEAK  # May is non-summer now
    assert t.tier_at(at(2026, 5, 25, 18)) == s.ON_PEAK  # Memorial Day no longer a holiday
    assert t.is_holiday(date(2026, 2, 2)) and not t.is_holiday(date(2026, 12, 25))


def test_observed_none_and_after_rule():
    raw = mutated()
    raw["holidays"]["observed"] = "none"
    t = s.parse_tariff(raw)
    assert t.is_holiday(date(2026, 7, 4)) and not t.is_holiday(date(2026, 7, 3))
    assert t.holiday_name(date(2026, 11, 27)) == "Day after Thanksgiving"


@pytest.mark.parametrize(
    "edit, message",
    [
        (lambda r: r["seasons"].update(summer=[5, 6, 7, 8, 9, 10]), "both"),
        (lambda r: r["seasons"].update(non_summer=[10, 11, 12]), "not assigned"),
        (lambda r: r["rates"].pop("on_peak"), "on_peak"),
        (lambda r: r["periods"][0].update(tier="bogus"), "tier must be"),
        (lambda r: r["periods"][0].update(days="sometimes"), "days must be"),
        (lambda r: r["periods"][1]["hours"].update(non_summer=[[1, 5], [4, 8]]), "overlap"),
        (lambda r: r["periods"][1]["hours"].update(non_summer=[[5, 1]]), "start < end"),
        (lambda r: r["periods"][0]["hours"].update(autumn=[[1, 2]]), "unknown season"),
        (lambda r: r["critical_peak"].update(replaces="discount_x"), "no period"),
        (lambda r: r["critical_peak"].update(max_shift_hours=9), "0-24"),
        (lambda r: r["holidays"].update(observed="sometimes"), "observed"),
        (lambda r: r["holidays"]["rules"].append({"name": "X", "after": "Nope", "days": 1}), "earlier rule"),
        (lambda r: r["holidays"]["rules"].append({"name": "X", "month": 2, "day": 30}), "day is out of range"),
        (lambda r: r["holidays"]["rules"].append({"name": "X"}), "needs"),
    ],
)
def test_validation_errors(edit, message):
    raw = copy.deepcopy(RAW)
    edit(raw)
    with pytest.raises(s.TariffError, match=message):
        s.parse_tariff(raw)


def test_load_errors(tmp_path):
    with pytest.raises(s.TariffError, match="cannot read"):
        s.load_tariff(tmp_path / "missing.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("this is = = not toml")
    with pytest.raises(s.TariffError, match="invalid TOML"):
        s.load_tariff(bad)
