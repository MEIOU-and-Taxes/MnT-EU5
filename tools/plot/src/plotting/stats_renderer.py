import numpy as np
from matplotlib.ticker import MaxNLocator

from src.constants import PERCENTILE_BY_ID, STAT_COLORS
from src.plotting.plot_common import MARGIN_BETWEEN_BORDERS_AND_OUTER_DATA_POINTS, _draw_horizontal_axis
from src.plotting.series_stats import _calculate_series_stats

STATS_UPPER_BANDS = [
	("p75", "p95", "#00ff00"),
	("p95", "p99", "#008000"),
	("p99", "max", "#000d00"),
]
STATS_LOWER_BANDS = [
	("p05", "p25", "#ff0000"),
	("p01", "p05", "#800000"),
	("min", "p01", "#0d0000"),
]
STATS_OUTER_PAIRS = [
	("min", "max"),
	("p01", "p99"),
	("p05", "p95"),
]
STATS_BAND_ALPHA = 0.15
STATS_IQR_COLOR_FULL = "#ffee00"
STATS_IQR_ALPHA_FULL = 0.20
STATS_IQR_COLOR_CLASSIC = "#8bc34a"
STATS_IQR_ALPHA_CLASSIC = 0.15
STATS_OUTER_COLOR = "#2e7d32"
STATS_OUTER_ALPHA = 0.04

def _render_stats_mode(ax, filtered_data, value_key, value_label, display_title, entity_key,
					   hide_level, on_stats_computed, on_lines_plotted, get_is_moving_avg, get_period_value,
					   get_stats_shading_all=lambda: False, is_year_offset=False,
					   is_ratio_mode=False, base_year_disp=None):
	ax._is_stats_mode_chart = True
	moments_dict = {}
	country_series = {}
	for item in filtered_data:
		m = item['moment']
		val = item[value_key]
		ent = item.get(entity_key, item.get('country', item.get('region', '')))
		moments_dict.setdefault(m, []).append((ent, val))
		country_series.setdefault(ent, {})[m] = val

	sorted_moments = sorted(moments_dict.keys())
	offset = 1337 if is_year_offset else 0
	x_coords = [m - offset for m in sorted_moments]

	hide_map = {
		0: ["max", "p99", "p95", "p75", "p50", "p25", "p05", "p01", "min"],
		1: ["p99", "p95", "p75", "p50", "p25", "p05", "p01"],
		2: ["p95", "p75", "p50", "p25", "p05"],
		3: ["p75", "p50", "p25"]
	}
	active_ids = hide_map.get(hide_level, hide_map[0])
	stat_curves = {s_id: [] for s_id in active_ids}

	for m in sorted_moments:
		vals = sorted([x[1] for x in moments_dict[m]])
		for s_id in active_ids:
			p = PERCENTILE_BY_ID[s_id][2]
			if p == 100:
				stat_curves[s_id].append(vals[-1])
			elif p == 0:
				stat_curves[s_id].append(vals[0])
			elif p == 50:
				stat_curves[s_id].append(float(np.median(vals)))
			else:
				# Use nearest-rank interpolation to prevent artificial fractional values in discrete data
				try:
					stat_curves[s_id].append(float(np.percentile(vals, p, method='nearest')))
				except TypeError:
					# Compatibility with NumPy < 1.22
					stat_curves[s_id].append(float(np.percentile(vals, p, interpolation='nearest')))

	is_ma = get_is_moving_avg()
	period = get_period_value()
	if is_ma and period > 1:
		for s_id in stat_curves:
			curve = stat_curves[s_id]
			if len(curve) > 1:
				stat_curves[s_id] = [
					sum(curve[max(0, i - period + 1):i + 1]) / len(curve[max(0, i - period + 1):i + 1])
					for i in range(len(curve))
				]

	ax._stats_moments_data = moments_dict
	all_values = [i[value_key] for i in filtered_data]
	global_stats = _calculate_series_stats(country_series, all_values, value_label)
	ax._global_stats = global_stats

	for s_id in active_ids:
		name = PERCENTILE_BY_ID[s_id][1]
		color = STAT_COLORS[s_id]
		ax.plot(x_coords, stat_curves[s_id], marker='o', linewidth=2, label=name, color=color)

	has_iqr = "p25" in stat_curves and "p75" in stat_curves

	if get_stats_shading_all():
		if has_iqr:
			ax.fill_between(x_coords, stat_curves["p25"], stat_curves["p75"],
							color=STATS_IQR_COLOR_FULL, alpha=STATS_IQR_ALPHA_FULL,
							label='IQR (25%-75%)')
		for low_id, high_id, color in STATS_UPPER_BANDS + STATS_LOWER_BANDS:
			if low_id in stat_curves and high_id in stat_curves:
				ax.fill_between(x_coords, stat_curves[low_id], stat_curves[high_id],
								color=color, alpha=STATS_BAND_ALPHA)
	else:
		if has_iqr:
			ax.fill_between(x_coords, stat_curves["p25"], stat_curves["p75"],
							color=STATS_IQR_COLOR_CLASSIC, alpha=STATS_IQR_ALPHA_CLASSIC,
							label='IQR (25%-75%)')
		for low_id, high_id in [("min", "max"), ("p01", "p99"), ("p05", "p95")]:
			if low_id in stat_curves and high_id in stat_curves:
				ax.fill_between(x_coords, stat_curves[low_id], stat_curves[high_id],
								color=STATS_OUTER_COLOR, alpha=STATS_OUTER_ALPHA)
				break

	ax.set_xlabel("Relative year" if is_year_offset else "Year")
	ax.xaxis.set_major_locator(MaxNLocator(integer=True))
	ax.ticklabel_format(useOffset=False, style='plain', axis='x')
	ax.set_ylabel(value_label)
	if is_ratio_mode and base_year_disp:
		ax.set_title(f"Statistical Distribution: Relative change from time {base_year_disp} for {display_title}")
	else:
		ax.set_title(f"Statistical Distribution: {display_title}")
	ax.legend(loc="upper left", ncol=2 if len(active_ids) > 5 else 1, fontsize=9, framealpha=0.85)
	ax._current_legend = ax.legend(loc="upper left", ncol=2 if len(active_ids) > 5 else 1, fontsize=9, framealpha=0.85)

	ax.margins(x=MARGIN_BETWEEN_BORDERS_AND_OUTER_DATA_POINTS)
	_draw_horizontal_axis(ax)

	if on_stats_computed:
		on_stats_computed(global_stats)

	ax.figure.canvas.draw_idle()
	on_lines_plotted()