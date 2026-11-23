# Duke Energy time-of-use for Home Assistant

A custom integration (`duke_tou`) that tells Home Assistant which time-of-use tier your Duke Energy Progress (NC) rate plan is in right now, and what a kWh costs. It has no cloud access or credentials: the tier follows the tariff calendar. For plans with critical peak days it also gives you a manual override, because Duke only notifies customers by phone, email or text.

## Rate plans
Pick one when you add the integration; change it later from the integration's menu, Reconfigure (that resets any rate overrides).

| Plan | Tariff | Notes |
|---|---|---|
| R-TOU-CPP | Leaf 503, 2025-10-01 | on-peak, off-peak, discount, plus critical peak days |
| R-TOU | Leaf 502, 2025-10-01 | same hours as R-TOU-CPP, no critical peak |
| R-TOUD | Leaf 501, 2025-10-01 | same hours; the price sensor covers energy charges only, not the kW demand charges |
| R-TOU-EV (pilot) | Leaf 504, 2026-01-01 | "Standard" and "Discount" (11 pm to 5 am daily, all year) |

## Install
Install with HACS (add this repository as a custom repository, category Integration), or copy `custom_components/duke_tou` into your Home Assistant config directory's `custom_components/`. Restart, then Settings > Devices & services > Add integration > "Duke Energy Time-of-Use".

## Tariffs are files
Everything about a plan's schedule lives in a file under [tariffs/](custom_components/duke_tou/tariffs/) (R-TOU-CPP is the fully commented one): seasons, on-peak and discount windows, holiday rules (fixed dates, nth weekdays, Easter offsets, "day after", and the Saturday/Sunday observance rule), the optional critical peak window and its allowed shift, display labels for tiers (EV calls off-peak "Standard"), and the default rates. For R-TOU-CPP that means:
- Summer is May to September; on-peak (Mon-Fri, not holidays) is 6-9 pm in summer and 6-9 am otherwise; discount is 1-6 am in summer and 1-3 am plus 11 am-4 pm otherwise; everything else is off-peak.
- Holidays: New Year's Day, Good Friday, Memorial Day, July 4, Labor Day, Thanksgiving and the day after, Christmas. A Saturday holiday is observed the Friday before, a Sunday holiday the Monday after.
- Critical peak: the on-peak window on days you flag, optionally shifted an hour. Duke can call 20 days a year (more in an emergency); the count is shown as an attribute.

When Duke revises a tariff, copy its file to `<Home Assistant config>/duke_tou/` under the same name and edit the copy; it is used instead of the bundled one. Any other `.toml` file you put there shows up as an extra choice in the plan picker. The integration refuses to load (with the reason in the log) if the file is inconsistent: overlapping hours, a month in two seasons, an unknown holiday rule, and so on. Tier ids stay fixed (`critical_peak`, `on_peak`, `off_peak`, `discount`). Keep top-level keys such as `default_tier` above the first `[table]` or TOML files them under that table.

Rates can also be changed under Configure (cents/kWh); an option overrides the file's rate, and the "all-in adder" stands in for riders, REPS, the storm charge and sales tax.

## Entities
The four critical peak entries below, and the services, exist only for plans with critical peak days (R-TOU-CPP). Entity ids keep the name of the plan you first chose, so switching plans does not break dashboards.
| Entity | Purpose |
|---|---|
| `sensor.…_tier` | `discount`, `off_peak`, `on_peak`, `critical_peak` (attributes: `label` such as "Standard", season, holiday, critical days used) |
| `sensor.…_price` | Current USD/kWh including the adder |
| `sensor.…_next_change`, `…_next_tier` | When and to what the tier changes next |
| `sensor.…_season` | `summer` or `non_summer` (the plan's own season names), with attributes `on_peak_hours`, `on_peak_start`, `on_peak_end` for that season, and `next_season`, `next_season_start`, `next_season_on_peak_hours`. Use it to pick pre-heat or pre-cool hours without hard-coding them |
| `sensor.…_next_peak_start` | When the next on-peak (or critical peak) window begins. Skips weekends and holidays, and follows a flagged critical day. Use it to start pre-heating or pre-cooling ahead of the peak |
| `binary_sensor.…_critical_peak_active` | On during the critical window |
| `binary_sensor.…_critical_peak_today_or_tomorrow` | On once a day is flagged, before the window starts |
| `switch.…_critical_peak_today` / `…_tomorrow` | The manual override: flip it when Duke's notice arrives |
| `select.…_critical_peak_window` | Earlier / Standard / Later, for when Duke shifts the window |

Services `duke_tou.set_critical_peak` and `duke_tou.clear_critical_peak` take a `date`, for automations. Flags persist across restarts.

Decision: an hour moved out of a shifted critical window reverts to its normal tier (on-peak), since the tariff does not say otherwise. Check the first shifted day against your bill.

## Development
```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/pytest
```
`tests/test_schedule.py` covers the tariff engine and file validation without Home Assistant; `tests/test_integration.py` runs the integration inside a test Home Assistant instance.
