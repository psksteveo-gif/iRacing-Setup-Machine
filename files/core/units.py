"""
Unit conversion helpers.
Call configure() once at startup with values from the user config.
All display code imports this module and calls the helpers — no restarts needed
for units to take effect after a session reload.
"""

_speed: str = 'kmh'   # 'kmh' or 'mph'
_temp:  str = 'c'     # 'c'   or 'f'


def configure(speed: str = 'kmh', temp: str = 'c') -> None:
    """Apply user preferences.  Call before rendering any charts/labels."""
    global _speed, _temp
    _speed = speed
    _temp  = temp


# ── Speed ─────────────────────────────────────────────────────────────────────

def speed_factor() -> float:
    """Multiplier to convert m/s → display unit."""
    return 2.23694 if _speed == 'mph' else 3.6

def speed_label() -> str:
    return 'mph' if _speed == 'mph' else 'km/h'

def fmt_speed(ms: float, decimals: int = 0) -> str:
    """Format a speed value from m/s."""
    return f"{ms * speed_factor():.{decimals}f} {speed_label()}"

def speed_from_kmh(kmh: float) -> float:
    """Convert an already-km/h value to the display unit."""
    return kmh * 0.621371 if _speed == 'mph' else kmh

def fmt_speed_from_kmh(kmh: float, decimals: int = 1) -> str:
    return f"{speed_from_kmh(kmh):.{decimals}f} {speed_label()}"


# ── Temperature ───────────────────────────────────────────────────────────────

def temp_label() -> str:
    return '°F' if _temp == 'f' else '°C'

def fmt_temp(celsius: float, decimals: int = 1) -> str:
    """Format a temperature value from °C."""
    if _temp == 'f':
        return f"{celsius * 9 / 5 + 32:.{decimals}f}°F"
    return f"{celsius:.{decimals}f}°C"
