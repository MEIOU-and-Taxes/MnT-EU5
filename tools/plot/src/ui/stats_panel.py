def format_stats_panel_text(global_stats: dict, year_stats: dict = None) -> str:
    """Formats the text to render inside the sidebar statistical overview panel."""
    if not global_stats:
        return ""

    y_label = global_stats.get('value_label', '')
    fmt = ",.0f" if y_label in ("Population", "Count") else ",.2f"

    lines = []
    if year_stats:
        lines.append(f"=== STATS FOR {year_stats['year']} ===")
        lines.append(f"Count:      {year_stats['count']}")
        lines.append(f"Mean:       {year_stats['mean']:{fmt}}")
        lines.append(f"Median:     {year_stats['median']:{fmt}}")
        lines.append(f"Std Dev:    {year_stats['std']:{fmt}}")

        prev_y = year_stats.get('prev_year')
        year_increases = year_stats.get('biggest_increase', [])
        year_decreases = year_stats.get('biggest_decrease', [])

        if prev_y is not None and year_increases:
            lines.append(f"\n--- BIGGEST GAINERS ({prev_y} → {year_stats['year']}) ---")
            for reg, delta, start, end in year_increases:
                lines.append(f"{reg[:12]:<12}: +{delta:{fmt}} ({start:{fmt}} → {end:{fmt}})")

        if prev_y is not None and year_decreases:
            lines.append(f"\n--- BIGGEST DECLINES ({prev_y} → {year_stats['year']}) ---")
            for reg, delta, start, end in year_decreases:
                lines.append(f"{reg[:12]:<12}: {delta:{fmt}} ({start:{fmt}} → {end:{fmt}})")
    else:
        lines.append("Hover plot to see yearly stats")

    lines.append("\n" + "=" * 30 + "\n")
    lines.append("=== GLOBAL OVERVIEW ===")
    lines.append(f"Avg Mean:   {global_stats['overall_mean']:{fmt}}")
    lines.append(f"Avg StdDev: {global_stats['overall_std']:{fmt}}")

    lines.append("\n--- BIGGEST GAINERS (Full Game) ---")
    for reg, delta, start, end, _ in global_stats['biggest_increase']:
        lines.append(f"{reg[:12]:<12}: +{delta:{fmt}} ({start:{fmt}} → {end:{fmt}})")

    lines.append("\n--- BIGGEST DECLINES (Full Game) ---")
    for reg, delta, start, end, _ in global_stats['biggest_decrease']:
        lines.append(f"{reg[:12]:<12}: {delta:{fmt}} ({start:{fmt}} → {end:{fmt}})")

    lines.append("\n--- HIGHEST VOLATILITY (σ) ---")
    for reg, _, _, _, std in global_stats['most_volatile']:
        lines.append(f"{reg[:12]:<12}: σ = {std:{fmt}}")

    return "\n".join(lines)