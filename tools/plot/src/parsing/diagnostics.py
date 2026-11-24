def _format_mismatch_report(values, expected_headers):
	"""Generates a detailed diagnostic report when a column count mismatch occurs."""
	got = len(values)
	exp = len(expected_headers)
	yr = values[0] if got > 0 else "Unknown"
	tag = values[1] if got > 1 else "Unknown"
	country_name = values[2] if got > 2 else "Unknown"

	lines = [
		"=" * 85,
		f"[LOG PARSER WARNING] Country Record Column Mismatch!",
		f"  Received: {got} columns | Expected: {exp} columns",
		f"  Context:  Year = '{yr}', Tag = '{tag}', Name = '{country_name}'",
		"-" * 85
	]

	if got < exp:
		cutoff_header = expected_headers[got] if got < exp else "N/A"
		lines.append(f"  Reason: Line was truncated or torn by concurrent thread logging.")
		lines.append(f"  First missing column: index {got} ('{cutoff_header}')")
		lines.append(f"  Last 5 received values: {values[-5:]}")
		lines.append(f"\n  Columns around cutoff (index {max(0, got - 3)} to {min(exp - 1, got + 3)}):")
		for i in range(max(0, got - 3), min(exp, got + 4)):
			status = "--> [MISSING]" if i >= got else "	[OK]"
			val_preview = f"'{values[i]}'" if i < got else "<not present>"
			lines.append(f"	{status} index {i:<3} | {expected_headers[i]:<32} = {val_preview}")
	else:
		lines.append(f"  Reason: Line had {got - exp} unexpected extra values.")
		lines.append(f"  Extra values: {values[exp:]}")

	lines.append("=" * 85)
	return "\n".join(lines)