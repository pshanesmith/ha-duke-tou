"""Constants for the Duke Energy Time-of-Use integration."""
from dataclasses import replace
from pathlib import Path

from homeassistant.core import HomeAssistant

from .schedule import DEFAULT_TARIFF, TARIFF_DIR, CRITICAL_PEAK, DISCOUNT, OFF_PEAK, ON_PEAK, Rates, Tariff

DOMAIN = "duke_tou"
PLATFORMS = ["sensor", "binary_sensor", "switch", "select"]


TIER_OPTIONS = [DISCOUNT, OFF_PEAK, ON_PEAK, CRITICAL_PEAK]

# Options are entered in cents/kWh, as the tariff and bills show them.
CONF_ADDER = "adder_cents"
# One option per tier, in cents/kWh as the tariff and bills show them. An option
# overrides the tariff file's rate; absent means use the file.
RATE_OPTIONS = {
    CRITICAL_PEAK: "critical_peak_cents",
    ON_PEAK: "on_peak_cents",
    OFF_PEAK: "off_peak_cents",
    DISCOUNT: "discount_cents",
}

SHIFT_OPTIONS = {"earlier": -1, "standard": 0, "later": 1}

SIGNAL_UPDATE = f"{DOMAIN}_update"
STORAGE_VERSION = 1
SERVICE_SET_CRITICAL = "set_critical_peak"
SERVICE_CLEAR_CRITICAL = "clear_critical_peak"


def rates_from_options(tariff: Tariff, options: dict) -> Rates:
    overrides = {
        tier: round(options[key] / 100, 6) for tier, key in RATE_OPTIONS.items() if key in options
    }
    return replace(tariff.rates, adder=round(options.get(CONF_ADDER, 0.0) / 100, 6), **overrides)


CONF_TARIFF = "tariff"


def _custom_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(DOMAIN))


def list_tariffs(hass: HomeAssistant) -> dict[str, Path]:
    """Plan file stems to paths: bundled plans, plus any *.toml in
    <config>/duke_tou/, which replaces a bundled plan of the same name."""
    out = {p.stem: p for p in sorted(TARIFF_DIR.glob("*.toml"))}
    custom = _custom_dir(hass)
    if custom.is_dir():
        out.update({p.stem: p for p in sorted(custom.glob("*.toml"))})
    return out


def tariff_path(hass: HomeAssistant, stem: str = DEFAULT_TARIFF) -> Path:
    try:
        return list_tariffs(hass)[stem]
    except KeyError:
        raise FileNotFoundError(f"no tariff named {stem!r}") from None
