"""Time-of-use tariff engine: loads a tariff file and answers tier questions.

Pure Python with no Home Assistant imports so it can be unit tested on its
own. The shipped tariff is Duke Energy Progress (NC) Schedule R-TOU-CPP; see
tariffs/duke_progress_nc_r_tou_cpp.toml.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

DISCOUNT = "discount"
OFF_PEAK = "off_peak"
ON_PEAK = "on_peak"
CRITICAL_PEAK = "critical_peak"
TIERS = (DISCOUNT, OFF_PEAK, ON_PEAK, CRITICAL_PEAK)

BUNDLED_TARIFF = Path(__file__).parent / "tariffs" / "duke_progress_nc_r_tou_cpp.toml"

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_DAY_KINDS = ("all", "weekdays", "weekdays_no_holidays")


class TariffError(ValueError):
    """The tariff file is missing something or contradicts itself."""


@dataclass(frozen=True)
class Rates:
    """Energy charges in dollars per kWh, plus a flat all-in adder.

    The adder stands in for riders, REPS, the storm charge and sales tax,
    which a tariff leaf leaves to other leaves.
    """

    critical_peak: float = 0.0
    on_peak: float = 0.0
    off_peak: float = 0.0
    discount: float = 0.0
    adder: float = 0.0

    def base(self, tier: str) -> float:
        return getattr(self, tier)

    def price(self, tier: str) -> float:
        return self.base(tier) + self.adder


Ranges = tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Period:
    tier: str
    days: str
    hours: Mapping[str, Ranges]  # season name -> [start, end) ranges


@dataclass(frozen=True)
class HolidayRule:
    name: str
    month: int | None = None
    day: int | None = None
    weekday: int | None = None
    nth: int | None = None
    easter_offset: int | None = None
    after: str | None = None
    days: int = 0


def easter(year: int) -> date:
    """Gregorian Easter (anonymous algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """nth weekday of a month; n=-1 is the last one."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


@dataclass
class Tariff:
    name: str
    rates: Rates  # file defaults, in dollars per kWh
    seasons: Mapping[str, tuple[int, ...]]
    periods: tuple[Period, ...]
    default_tier: str
    critical_replaces: str
    max_shift_hours: int
    critical_days_per_year: int
    observed: str
    holiday_rules: tuple[HolidayRule, ...]
    _holiday_cache: dict[int, dict[date, str]] = field(default_factory=dict, repr=False)

    # --- calendar -------------------------------------------------------

    def season(self, d: date) -> str:
        for name, months in self.seasons.items():
            if d.month in months:
                return name
        raise AssertionError("validated: every month has a season")

    def holiday_dates(self, year: int) -> dict[date, str]:
        """Holidays for a year as observed. May include Dec 31 of the previous
        year (a Saturday New Year's Day is observed the Friday before)."""
        cached = self._holiday_cache.get(year)
        if cached is not None:
            return cached
        base: dict[str, date] = {}
        for r in self.holiday_rules:
            if r.after is not None:
                d = base[r.after] + timedelta(days=r.days)
            elif r.easter_offset is not None:
                d = easter(year) + timedelta(days=r.easter_offset)
            elif r.weekday is not None:
                d = _nth_weekday(year, r.month, r.weekday, r.nth)
            else:
                d = date(year, r.month, r.day)
            base[r.name] = d
        out: dict[date, str] = {}
        for name, d in base.items():
            if self.observed == "nearest_weekday":
                if d.weekday() == 5:
                    d -= timedelta(days=1)
                elif d.weekday() == 6:
                    d += timedelta(days=1)
            out[d] = name
        self._holiday_cache[year] = out
        return out

    def holiday_name(self, d: date) -> str | None:
        for year in (d.year, d.year + 1):
            name = self.holiday_dates(year).get(d)
            if name:
                return name
        return None

    def is_holiday(self, d: date) -> bool:
        return self.holiday_name(d) is not None

    # --- tiers ----------------------------------------------------------

    def _applies(self, p: Period, d: date) -> bool:
        if p.days == "all":
            return True
        if d.weekday() >= 5:
            return False
        return p.days == "weekdays" or not self.is_holiday(d)

    def base_tier(self, d: date, hour: int) -> str:
        """Tier ignoring critical peak days."""
        season = self.season(d)
        for p in self.periods:
            if self._applies(p, d) and any(s <= hour < e for s, e in p.hours.get(season, ())):
                return p.tier
        return self.default_tier

    def critical_window(self, d: date, shift: int = 0) -> Ranges:
        """Hours billed as critical peak on a flagged day, shifted by `shift`."""
        season = self.season(d)
        for p in self.periods:
            if p.tier == self.critical_replaces:
                return tuple((s + shift, e + shift) for s, e in p.hours.get(season, ()))
        return ()

    def tier_at(self, now: datetime, critical_days: Mapping[date, int] | None = None) -> str:
        """Tier at a local datetime.

        `critical_days` maps each called critical peak day to its window shift
        in hours. A called day is honoured on any weekday or holiday.
        """
        d = now.date()
        if critical_days and d in critical_days:
            if any(s <= now.hour < e for s, e in self.critical_window(d, critical_days[d])):
                return CRITICAL_PEAK
        return self.base_tier(d, now.hour)

    def next_change(
        self,
        now: datetime,
        critical_days: Mapping[date, int] | None = None,
        horizon_hours: int = 96,
    ) -> tuple[datetime, str] | None:
        """The next top of the hour at which the tier differs, with the new tier.

        Boundaries fall on whole local hours, so an hourly scan is exact.
        Returns None if nothing changes within the horizon.
        """
        current = self.tier_at(now, critical_days)
        t = now.replace(minute=0, second=0, microsecond=0)
        for _ in range(horizon_hours):
            t = _add_hour(t)
            tier = self.tier_at(t, critical_days)
            if tier != current:
                return t, tier
        return None


def _add_hour(t: datetime) -> datetime:
    """Add one real hour, staying correct across DST for aware datetimes."""
    if t.tzinfo is None:
        return t + timedelta(hours=1)
    return (t.astimezone(timezone.utc) + timedelta(hours=1)).astimezone(t.tzinfo)


# --- loading and validation --------------------------------------------------


def format_ranges(ranges: Ranges) -> str:
    return ", ".join(f"{s:02d}:00-{e:02d}:00" for s, e in ranges)


def load_tariff(path: Path | str) -> Tariff:
    path = Path(path)
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except OSError as err:
        raise TariffError(f"cannot read tariff {path}: {err}") from err
    except tomllib.TOMLDecodeError as err:
        raise TariffError(f"{path}: invalid TOML: {err}") from err
    try:
        return parse_tariff(raw)
    except TariffError as err:
        raise TariffError(f"{path}: {err}") from err


def _need(table: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in table:
        raise TariffError(f"missing '{key}' in {where}")
    return table[key]


def _int(value: Any, where: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise TariffError(f"{where} must be an integer from {lo} to {hi}, got {value!r}")
    return value


def _ranges(value: Any, where: str) -> Ranges:
    if not isinstance(value, list):
        raise TariffError(f"{where} must be a list of [start, end] pairs")
    out = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            raise TariffError(f"{where}: each range must be [start, end], got {pair!r}")
        s, e = _int(pair[0], where, 0, 24), _int(pair[1], where, 0, 24)
        if s >= e:
            raise TariffError(f"{where}: range [{s}, {e}] must have start < end")
        out.append((s, e))
    out.sort()
    for (_, e1), (s2, _) in zip(out, out[1:]):
        if s2 < e1:
            raise TariffError(f"{where}: ranges overlap")
    return tuple(out)


def parse_tariff(raw: Mapping[str, Any]) -> Tariff:
    name = str(raw.get("name", "tariff"))

    rates_raw = _need(raw, "rates", "tariff")
    rates = {}
    for tier in TIERS:
        v = _need(rates_raw, tier, "[rates]")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise TariffError(f"[rates] {tier} must be a non-negative number, got {v!r}")
        rates[tier] = round(v / 100, 6)

    seasons_raw = _need(raw, "seasons", "tariff")
    seasons: dict[str, tuple[int, ...]] = {}
    seen: dict[int, str] = {}
    for sname, months in seasons_raw.items():
        if not isinstance(months, list):
            raise TariffError(f"[seasons] {sname} must be a list of months")
        for m in months:
            _int(m, f"[seasons] {sname}", 1, 12)
            if m in seen:
                raise TariffError(f"month {m} is in both '{seen[m]}' and '{sname}'")
            seen[m] = sname
        seasons[sname] = tuple(months)
    missing = sorted(set(range(1, 13)) - set(seen))
    if missing:
        raise TariffError(f"[seasons] months not assigned to a season: {missing}")

    periods = []
    for i, p in enumerate(raw.get("periods", [])):
        where = f"[[periods]] #{i + 1}"
        tier = _need(p, "tier", where)
        if tier not in TIERS or tier == CRITICAL_PEAK:
            raise TariffError(f"{where}: tier must be one of {[t for t in TIERS if t != CRITICAL_PEAK]}")
        days = _need(p, "days", where)
        if days not in _DAY_KINDS:
            raise TariffError(f"{where}: days must be one of {list(_DAY_KINDS)}")
        hours_raw = _need(p, "hours", where)
        for sname in hours_raw:
            if sname not in seasons:
                raise TariffError(f"{where}: unknown season '{sname}' in hours")
        periods.append(
            Period(tier, days, {s: _ranges(r, f"{where} hours.{s}") for s, r in hours_raw.items()})
        )

    default_tier = _need(raw, "default_tier", "tariff")
    if default_tier not in TIERS or default_tier == CRITICAL_PEAK:
        raise TariffError(f"default_tier must be one of {[t for t in TIERS if t != CRITICAL_PEAK]}")

    cp = _need(raw, "critical_peak", "tariff")
    replaces = _need(cp, "replaces", "[critical_peak]")
    target = [p for p in periods if p.tier == replaces]
    if not target:
        raise TariffError(f"[critical_peak] replaces '{replaces}', which has no period")
    max_shift = _int(_need(cp, "max_shift_hours", "[critical_peak]"), "max_shift_hours", 0, 12)
    per_year = _int(cp.get("days_per_year", 0), "days_per_year", 0, 366)
    for p in target:
        for sname, rs in p.hours.items():
            for s, e in rs:
                if s - max_shift < 0 or e + max_shift > 24:
                    raise TariffError(
                        f"[critical_peak] shifting {replaces} {sname} hours by "
                        f"{max_shift} would leave the 0-24 day"
                    )

    hol = raw.get("holidays", {})
    observed = hol.get("observed", "none")
    if observed not in ("none", "nearest_weekday"):
        raise TariffError("[holidays] observed must be 'none' or 'nearest_weekday'")
    rules: list[HolidayRule] = []
    names: set[str] = set()
    for i, r in enumerate(hol.get("rules", [])):
        where = f"[holidays] rule #{i + 1}"
        rname = _need(r, "name", where)
        if rname in names:
            raise TariffError(f"{where}: duplicate name '{rname}'")
        if "after" in r:
            if r["after"] not in names:
                raise TariffError(f"{where}: 'after' must name an earlier rule, got {r['after']!r}")
            rule = HolidayRule(rname, after=r["after"], days=_int(_need(r, "days", where), where, -31, 31))
        elif "easter_offset" in r:
            rule = HolidayRule(rname, easter_offset=_int(r["easter_offset"], where, -60, 60))
        elif "weekday" in r:
            wd = r["weekday"]
            if wd not in _WEEKDAYS:
                raise TariffError(f"{where}: weekday must be one of {list(_WEEKDAYS)}")
            nth = _int(_need(r, "nth", where), where, -1, 5)
            if nth == 0:
                raise TariffError(f"{where}: nth must be 1-5 or -1 (last)")
            rule = HolidayRule(rname, month=_int(_need(r, "month", where), where, 1, 12),
                               weekday=_WEEKDAYS[wd], nth=nth)
        elif "day" in r:
            month, day = _int(_need(r, "month", where), where, 1, 12), _int(r["day"], where, 1, 31)
            try:
                date(2024, month, day)
            except ValueError as err:
                raise TariffError(f"{where}: {err}") from err
            rule = HolidayRule(rname, month=month, day=day)
        else:
            raise TariffError(f"{where}: needs month+day, month+weekday+nth, easter_offset or after+days")
        names.add(rname)
        rules.append(rule)

    return Tariff(
        name=name,
        rates=Rates(**rates),
        seasons=seasons,
        periods=tuple(periods),
        default_tier=default_tier,
        critical_replaces=replaces,
        max_shift_hours=max_shift,
        critical_days_per_year=per_year,
        observed=observed,
        holiday_rules=tuple(rules),
    )
