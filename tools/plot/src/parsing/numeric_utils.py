import re
import numpy as np

def parse_dynamic_numeric_value(value_str):
    """Converts K/M/B suffixed or comma-formatted numbers to floats."""
    if not isinstance(value_str, str):
        return value_str

    cleaned_str = re.sub(r'[\x00-\x1f§]|%?NAK[A-Z!]%?', '', value_str)
    cleaned_str = cleaned_str.strip().replace(',', '').replace('%', '').replace('+', '')

    if not cleaned_str:
        return 0.0

    upper_str = cleaned_str.upper()
    multiplier = 1.0

    if upper_str.endswith('K'):
        multiplier = 1_000.0
        cleaned_str = cleaned_str[:-1]
    elif upper_str.endswith('M'):
        multiplier = 1_000_000.0
        cleaned_str = cleaned_str[:-1]
    elif upper_str.endswith('B'):
        multiplier = 1_000_000_000.0
        cleaned_str = cleaned_str[:-1]

    try:
        return float(cleaned_str) * multiplier
    except (ValueError, TypeError):
        return value_str


def format_metric_3digits(val, show_plus=False) -> str:
    """
    Formats a numeric value using metric prefixes (K, M, B, T) with exactly 3 digits:
    """
    if val is None:
        return ""
    try:
        num = float(val)
    except (ValueError, TypeError):
        return str(val)

    if np.isnan(num):
        return "NaN"

    is_negative = num < 0
    abs_num = abs(num)

    if is_negative:
        sign = "-"
    elif show_plus and abs_num > 1e-9:
        sign = "+"
    else:
        sign = " "

    if abs_num < 1e-9:
        return f"{sign}0.00"

    units = [("", 1.0), ("K", 1e3), ("M", 1e6), ("B", 1e9), ("T", 1e12)]

    unit_idx = 0
    while unit_idx < len(units) - 1 and abs_num >= units[unit_idx + 1][1] * 0.9995:
        unit_idx += 1

    suffix, factor = units[unit_idx]
    scaled = abs_num / factor

    if scaled >= 99.95:
        formatted = f"{scaled:.0f}"
    elif scaled >= 9.995:
        formatted = f"{scaled:.1f}"
    else:
        formatted = f"{scaled:.2f}"

    return f"{sign}{formatted}{suffix}"