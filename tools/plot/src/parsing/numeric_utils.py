import re

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