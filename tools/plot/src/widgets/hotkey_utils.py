def sort_hotkeys(keys):
    """Sorts hotkeys putting plain numbers (1..9, 0) first, followed by modifier combos."""
    def _sort_key(k):
        tokens = [t.strip() for t in k.split('+') if t.strip()]
        has_ctrl = any(t.lower() == 'ctrl' for t in tokens)
        has_alt = any(t.lower() == 'alt' for t in tokens)
        has_shift = any(t.lower() == 'shift' for t in tokens)
        base = [t for t in tokens if t.lower() not in ('ctrl', 'alt', 'shift')]
        base_str = base[0] if base else ""

        mod_score = (1 if has_ctrl else 0) * 1 + (2 if has_alt else 0) * 2 + (4 if has_shift else 0) * 4

        if base_str.isdigit():
            val = int(base_str)
            num_order = 10 if val == 0 else val
        elif base_str.startswith('F') and base_str[1:].isdigit():
            num_order = 100 + int(base_str[1:])
        else:
            num_order = 999

        return (mod_score, num_order, base_str)

    return sorted(keys, key=_sort_key)
