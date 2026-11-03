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