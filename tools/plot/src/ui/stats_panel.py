def format_stats_panel_text(global_stats: dict, year_stats: dict = None) -> str:
    """Formats the text to render inside the sidebar statistical overview panel."""
    if not global_stats:
        return ""

    y_label = global_stats.get('value_label', '')
    fmt = ",.0f" if y_label in ("Population", "Count") else ",.2f"

    lines = []
    if year_stats:
        lines.append(f"=== Stats for {year_stats['year']} ===")
        lines.append(f"Count:      {year_stats['count']}")
        lines.append(f"Mean:       {year_stats['mean']:{fmt}}")
        lines.append(f"Median:     {year_stats['median']:{fmt}}")
        lines.append(f"Std Dev:    {year_stats['std']:{fmt}}")

        prev_y = year_stats.get('prev_year')
        year_increases = year_stats.get('biggest_increase', [])
        year_decreases = year_stats.get('biggest_decrease', [])

        if prev_y is not None and year_increases:
            lines.append(f"\n--- Top increases ({prev_y} → {year_stats['year']}) ---")
            for reg, delta, start, end in year_increases:
                lines.append(f"{reg[:12]:<12}: +{delta:{fmt}} ({start:{fmt}} → {end:{fmt}})" if delta > 0 else "")

        if prev_y is not None and year_decreases:
            lines.append(f"\n--- Top decreases ({prev_y} → {year_stats['year']}) ---")
            for reg, delta, start, end in year_decreases:
                lines.append(f"{reg[:12]:<12}: {delta:{fmt}} ({start:{fmt}} → {end:{fmt}})" if delta < 0 else "")
    else:
        lines.append("Hover plot to see yearly stats")

    lines.append("\n=== Global overview ===")
    lines.append(f"Avg Mean:   {global_stats['overall_mean']:{fmt}}")
    lines.append(f"Avg StdDev: {global_stats['overall_std']:{fmt}}")

    lines.append("\n--- Top increases ---")
    for item in global_stats.get('biggest_increase', []):
        reg, delta, start, end = item[0], item[1], item[2], item[3]
        end_yr = item[6] if len(item) > 6 else ""
        yr_str = f", {end_yr}" if end_yr else ""
        lines.append(f"{reg[:12]:<12}: +{delta:{fmt}} ({start:{fmt}} → {end:{fmt}}{yr_str})" if delta > 0 else "")

    lines.append("\n--- Top decreases ---")
    for item in global_stats.get('biggest_decrease', []):
        reg, delta, start, end = item[0], item[1], item[2], item[3]
        end_yr = item[6] if len(item) > 6 else ""
        yr_str = f", {end_yr}" if end_yr else ""
        lines.append(f"{reg[:12]:<12}: {delta:{fmt}} ({start:{fmt}} → {end:{fmt}}{yr_str})" if delta < 0 else "")

    lines.append("\n--- Top standard deviation ---")
    for item in global_stats.get('most_volatile', []):
        reg, std = item[0], item[4]
        start_yr = item[5] if len(item) > 5 else None
        end_yr = item[6] if len(item) > 6 else None
        if start_yr and end_yr and start_yr != end_yr:
            yr_str = f" ({start_yr}-{end_yr})"
        elif end_yr:
            yr_str = f" ({end_yr})"
        else:
            yr_str = ""
        if std > 0:
            lines.append(f"{reg[:10]:<10}: {std:{fmt}}{yr_str}")

    return "\n".join(lines)