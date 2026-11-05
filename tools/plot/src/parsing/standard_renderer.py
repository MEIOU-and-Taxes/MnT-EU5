from itertools import cycle

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from src.constants import STR_ALL_REGIONS, STR_ALL_MOMENTS, SHOW_LEGEND
from src.plotting.plot_common import MARGIN_BETWEEN_BORDERS_AND_OUTER_DATA_POINTS, _draw_horizontal_axis
from src.plotting.series_stats import _calculate_series_stats


def _render_standard_mode(ax, filtered_data, m_filter, c_filter, r_filter, all_cat,
						  cat_key, val_key, val_label, add_zero, get_is_moving_avg, get_period,
						  config, on_stats_computed, on_lines_plotted,
						  entity_key="region", all_region_str=STR_ALL_REGIONS,
						  is_year_offset=False, is_ratio_mode=False, base_year_disp=None):
	ax._is_stats_mode_chart = False
	is_m_all = (m_filter == STR_ALL_MOMENTS)
	is_c_picked = (c_filter != all_cat)
	is_r_picked = (r_filter != all_region_str)
	colors = cycle(plt.rcParams['axes.prop_cycle'].by_key()['color'])
	offset = 1337 if is_year_offset else 0

	# Store per-moment raw values for summary statistics and stats panel
	moments_dict = {}
	country_series = {}
	for item in filtered_data:
		m = item['moment']
		val = item[val_key]
		ent = item.get(entity_key, item.get('country', item.get('region', '')))
		moments_dict.setdefault(m, []).append((ent, val))
		country_series.setdefault(ent, {})[m] = val

	ax._stats_moments_data = moments_dict
	all_values = [i[val_key] for i in filtered_data]
	global_stats = _calculate_series_stats(country_series, all_values, val_label)
	ax._global_stats = global_stats

	if on_stats_computed:
		on_stats_computed(global_stats)

	if is_m_all and (is_c_picked or is_r_picked):
		if is_r_picked and all_cat is None:
			plot_key = entity_key
		elif is_r_picked:
			plot_key = cat_key
		else:
			plot_key = entity_key

		series = {}
		for item in filtered_data:
			ent = item.get(plot_key, '')
			series.setdefault(ent, {'m': [], 'v': []})
			series[ent]['m'].append(item['moment'] - offset)
			series[ent]['v'].append(item[val_key])

		if add_zero and series:
			all_m = [moment for v in series.values() for moment in v['m']]
			if all_m:
				overall_min_m = min(all_m)
				for values in series.values():
					if values['m']:
						line_min_m = min(values['m'])
						if line_min_m > overall_min_m:
							values['m'].append(line_min_m - 1)
							values['v'].append(0)

		ax.set_xlabel("Relative year" if is_year_offset else "Year")
		ax.xaxis.set_major_locator(MaxNLocator(integer=True))
		ax.set_ylabel(val_label)

		title_prefix = f"Relative change from time {base_year_disp}" if (is_ratio_mode and base_year_disp) else f"{val_label}"

		if is_r_picked and all_cat is None:
			if is_ratio_mode and base_year_disp:
				ax.set_title(f"{title_prefix}: {c_filter} for {r_filter}")
			else:
				ax.set_title(f"{c_filter} for {r_filter}")
		elif is_c_picked:
			ax.set_title(f"{title_prefix} for: {c_filter}")
		else:
			ax.set_title(f"{title_prefix} in: {r_filter}")

		marker = 'o' if len(set(i['moment'] for i in filtered_data)) <= 50 else None
		is_ma = get_is_moving_avg()
		p = get_period()

		for name, vals in sorted(series.items()):
			sm, sv = zip(*sorted(zip(vals['m'], vals['v'])))
			if is_ma and len(sv) > 1 and p > 1:
				ma_vals = [sum(sv[max(0, i - p + 1):i + 1]) / len(sv[max(0, i - p + 1):i + 1]) for i in range(len(sv))]
				ax.plot(sm, ma_vals, marker=marker, linestyle='-', label=name, color=next(colors))
			else:
				ax.plot(sm, sv, marker=marker, linestyle='-', label=name, color=next(colors))

		if series:
			min_x = min(min(v['m']) for v in series.values() if v['m'])
			max_x = max(max(v['m']) for v in series.values() if v['m'])
			span = max(1.0, max_x - min_x)
			pad = span * MARGIN_BETWEEN_BORDERS_AND_OUTER_DATA_POINTS
			ax.set_xlim(min_x - pad, max_x + pad)

		if "y_axis_limits" in config:
			ax.set_ylim(config["y_axis_limits"])
		if SHOW_LEGEND:
			ax.legend(bbox_to_anchor=(1.04, 1), loc="upper left")

	elif not is_m_all and (is_c_picked or is_r_picked):
		if is_r_picked and all_cat is None:
			color_key = entity_key
		elif is_r_picked:
			color_key = cat_key
		else:
			color_key = entity_key

		items = sorted(list(set(i.get(color_key, '') for i in filtered_data)))
		cmap = {n: next(colors) for n in items}
		labels = [str(i.get(color_key, '')) for i in filtered_data]
		values = [i[val_key] for i in filtered_data]
		b_colors = [cmap[i.get(color_key, '')] for i in filtered_data]

		ax.bar(labels, values, color=b_colors)
		ax.set_ylabel(val_label)
		time_display = f"Year: T+{m_filter}" if is_year_offset else f"Year: {m_filter}"
		ax.set_title(f"{val_label} for {time_display}")
		plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

		if items:
			patches = [mpatches.Patch(color=c, label=l) for l, c in cmap.items()]
			ax.legend(handles=patches, bbox_to_anchor=(1.04, 1), loc="upper left")
	else:
		ax.text(0.5, 0.5, "Please select a filter to display a graph.", ha='center', va='center')

	_draw_horizontal_axis(ax)
	ax.figure.canvas.draw_idle()
	on_lines_plotted()
