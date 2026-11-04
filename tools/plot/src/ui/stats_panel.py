def format_stats_panel_text(global_stats: dict, year_stats: dict = None) -> str:
    """Formats the text to render inside the sidebar statistical overview panel."""
    if not global_stats:
        return ""

    y_label = global_stats.get('value_label', '')
    fmt = ",.0f" if y_label in ("Population", "Count") else ",.2f"

    lines = []
    if year_stats:
        lines.append(f"====== Stats for {year_stats['year']} ======")
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

    lines.append("\n====== Global overview ======")
    lines.append(f"Avg Mean:   {global_stats['overall_mean']:{fmt}}")
    lines.append(f"Avg StdDev: {global_stats['overall_std']:{fmt}}")

    lines.append("\n--- Top consecutive increases ---")
    for item in global_stats.get('biggest_increase', []):
        reg, delta, start, end = item[0], item[1], item[2], item[3]
        y_to = item[5] if len(item) > 5 else ""
        yr_str = f", {y_to}" if (y_to) else ""
        lines.append(f"{reg[:10]:<10}: +{delta:{fmt}} ({start:{fmt}} → {end:{fmt}}{yr_str})" if delta > 0 else "")

    lines.append("\n--- Top consecutive decreases ---")
    for item in global_stats.get('biggest_decrease', []):
        reg, delta, start, end = item[0], item[1], item[2], item[3]
        y_to = item[5] if len(item) > 5 else ""
        yr_str = f", {y_to}" if (y_to) else ""
        lines.append(f"{reg[:10]:<10}: {delta:{fmt}} ({start:{fmt}} → {end:{fmt}}{yr_str})" if delta < 0 else "")

    lines.append("\n--- Top overall increases ---")
    for item in global_stats.get('overall_increase', []):
        reg, delta, start, end = item[0], item[1], item[2], item[3]
        y_from = item[4] if len(item) > 4 else ""
        y_to = item[5] if len(item) > 5 else ""
        yr_str = f", {y_from}→{y_to}" if (y_from and y_to) else ""
        if delta > 0:
            lines.append(f"{reg[:10]:<10}: +{delta:{fmt}} ({start:{fmt}} → {end:{fmt}}{yr_str})")

    lines.append("\n--- Top overall decreases ---")
    for item in global_stats.get('overall_decrease', []):
        reg, delta, start, end = item[0], item[1], item[2], item[3]
        y_from = item[4] if len(item) > 4 else ""
        y_to = item[5] if len(item) > 5 else ""
        yr_str = f", {y_from}→{y_to}" if (y_from and y_to) else ""
        if delta < 0:
            lines.append(f"{reg[:10]:<10}: {delta:{fmt}} ({start:{fmt}} → {end:{fmt}}{yr_str})")

    lines.append("\n--- Top standard deviation ---")
    for item in global_stats.get('most_volatile', []):
        reg, std = item[0], item[1]
        if std > 0:
            lines.append(f"{reg[:10]:<10}: {std:{fmt}}")

    return "\n".join(lines)