from src.parsing.numeric_utils import format_metric_3digits

NAME_WIDTH = 19
TOP_N = 5          # every "Top ..." section is padded to exactly this many rows
YEAR_OFFSET = 1337
YEAR_WIDTH = 4

def _fmt_year(y):
    """Right-align a year in a fixed 4-char field (blank if missing)."""
    if y is None or y == "":
        return " " * YEAR_WIDTH
    return f"{int(y):>{YEAR_WIDTH}}"

def _fmt(v):
    return format_metric_3digits(v)


def _fmt_plus(v):
    return format_metric_3digits(v, show_plus=True)


def _year(value, offset):
    """Return the display year, or "" if the value is missing."""
    if value is None or value == "":
        return ""
    return value - offset


def _delta_row(item, signed, offset, years="none"):
    """
    Build one 'region: delta (start -> end[, years])' row.

    years:
      "none" - no year info (per-year sections)
      "to"   - append ', <end year>'          (consecutive changes, item[5])
      "span" - append ', <from>→<to>'         (overall changes, item[4], item[5])
    """
    reg, delta, start, end = item[0], item[1], item[2], item[3]
    delta_str = _fmt_plus(delta) if signed else _fmt(delta)

    yr_str = ""
    if years == "to" and len(item) > 5:
        y_to = _year(item[5], offset)
        if y_to != "":
            yr_str = f": {_fmt_year(y_to)}"
    elif years == "span" and len(item) > 5:
        y_from = _year(item[4], offset)
        y_to = _year(item[5], offset)
        if y_from != "" and y_to != "":
            yr_str = f": {_fmt_year(y_from)}→{_fmt_year(y_to)}"

    return (
        f"{reg[:NAME_WIDTH]:<{NAME_WIDTH}}: {delta_str:6} "
        f"({_fmt(start):5} → {_fmt(end):5}{yr_str})"
    )


def _change_rows(items, direction, offset, years="none"):
    """Rows for increases (direction=+1) or decreases (direction=-1); other items are dropped."""
    rows = []
    for item in items or []:
        delta = item[1]
        if direction > 0 and delta > 0:
            rows.append(_delta_row(item, signed=True, offset=offset, years=years))
        elif direction < 0 and delta < 0:
            rows.append(_delta_row(item, signed=False, offset=offset, years=years))
    return rows


def _std_rows(items):
    rows = []
    for item in items or []:
        reg, std = item[0], item[1]
        if std > 0:
            rows.append(f"{reg[:NAME_WIDTH]:<{NAME_WIDTH}}: {_fmt(std)}")
    return rows


def _add_section(lines, title, rows, n=TOP_N):
    """Append a heading plus exactly n rows (real rows first, blank padding after)."""
    lines.append(f"\n--- {title} ---")
    rows = rows[:n]
    lines.extend(rows)
    lines.extend([""] * (n - len(rows)))


def format_stats_panel_text(global_stats: dict, year_stats: dict = None, is_year_offset: bool = False) -> str:
    """Formats the text to render inside the sidebar statistical overview panel."""
    if not global_stats:
        return ""

    offset = YEAR_OFFSET if is_year_offset else 0
    lines = []

    # ---- Per-year block -------------------------------------------------
    if year_stats:
        cur_y_disp = year_stats["year"] - offset
        lines.append(f"====== Stats for {_fmt_year(cur_y_disp)} ======")
        lines.append(f"Count:      {year_stats['count']}")
        lines.append(f"Mean:       {_fmt(year_stats['mean'])}")
        lines.append(f"Median:     {_fmt(year_stats['median'])}")
        lines.append(f"Std Dev:    {_fmt(year_stats['std'])}")

        prev_y = year_stats.get("prev_year")
        if prev_y is not None:
            prev_y_disp = prev_y - offset
            span = f"({_fmt_year(prev_y_disp)} → {_fmt_year(cur_y_disp)})"
            _add_section(lines,f"Top increases {span}",_change_rows(year_stats.get("biggest_increase"), +1, offset))
            _add_section(lines,f"Top decreases {span}",_change_rows(year_stats.get("biggest_decrease"), -1, offset))
    else:
        lines.append("Hover plot to see yearly stats")

    # ---- Global block ---------------------------------------------------
    lines.append("\n====== Global overview ======")
    lines.append(f"Avg Mean:   {_fmt(global_stats['overall_mean'])}")
    lines.append(f"Avg StdDev: {_fmt(global_stats['overall_std'])}")

    _add_section(lines,"Top consecutive increases", _change_rows(global_stats.get("biggest_increase"), +1, offset, years="to"))
    _add_section(lines,"Top consecutive decreases", _change_rows(global_stats.get("biggest_decrease"), -1, offset, years="to"))
    _add_section(lines,"Top overall increases", _change_rows(global_stats.get("overall_increase"), +1, offset, years="span"))
    _add_section(lines,"Top overall decreases", _change_rows(global_stats.get("overall_decrease"), -1, offset, years="span"))
    _add_section(lines,"Top standard deviation", _std_rows(global_stats.get("most_volatile")),)

    return "\n".join(lines)