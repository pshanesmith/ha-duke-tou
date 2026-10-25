# Duke Energy R-TOU-CPP for Home Assistant

A custom integration (`duke_tou`) for Duke Energy Progress (NC) Schedule R-TOU-CPP, NC Second Revised Leaf No. 503, effective 2025-10-01. It has no cloud access or credentials: the tier follows the tariff calendar, and you flag critical peak days by hand because Duke only tells customers by phone, email or text.

## Install
Install with HACS (add this repository as a custom repository, category Integration), or copy `custom_components/duke_tou` into your Home Assistant config directory's `custom_components/`, restart, then Settings > Devices & services > Add integration > "Duke Energy Time-of-Use". 

## The tariff is a file
Everything about the schedule lives in [the bundled tariff file](custom_components/duke_tou/tariffs/duke_progress_nc_r_tou_cpp.toml): seasons, on-peak and discount windows, holiday rules (fixed dates, nth weekdays, Easter offsets, "day after", and the Saturday/Sunday observance rule), the critical peak window and its allowed shift, and the default rates. For this plan that means:
- Summer is May to September; on-peak (Mon-Fri, not holidays) is 6-9 pm in summer and 6-9 am otherwise; discount is 1-6 am in summer and 1-3 am plus 11 am-4 pm otherwise; everything else is off-peak.
- Holidays: New Year's Day, Good Friday, Memorial Day, July 4, Labor Day, Thanksgiving and the day after, Christmas. A Saturday holiday is observed the Friday before, a Sunday holiday the Monday after.
- Critical peak: the on-peak window on days you flag, optionally shifted an hour. Duke can call 20 days a year (more in an emergency); the count is shown as an attribute.

When Duke revises the tariff, copy the file to `<Home Assistant config>/duke_tou/tariff.toml` and edit it. That copy is used instead of the bundled one, and the integration refuses to load (with the reason in the log) if the file is inconsistent: overlapping hours, a month in two seasons, an unknown holiday rule, and so on. Tier names stay fixed (`critical_peak`, `on_peak`, `off_peak`, `discount`). Keep top-level keys such as `default_tier` above the first `[table]` or TOML files them under that table.

Rates can also be changed under Configure (cents/kWh); an option overrides the file's rate, and the "all-in adder" stands in for riders, REPS, the storm charge and sales tax.

## Entities
| Entity | Purpose |
|---|---|
| `sensor.…_tier` | `discount`, `off_peak`, `on_peak`, `critical_peak` (attributes: season, holiday, days used) |
| `sensor.…_price` | Current USD/kWh including the adder |
| `sensor.…_next_change`, `…_next_tier` | When and to what the tier changes next |
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
