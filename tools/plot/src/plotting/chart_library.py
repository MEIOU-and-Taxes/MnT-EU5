from itertools import cycle
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from PyQt6.QtWidgets import QLabel
from matplotlib.ticker import MaxNLocator

from src.constants import (
	STR_ALL_MOMENTS, STR_ALL_REGIONS, STAT_COLORS,
	POS_SUBPLOT_TOP_EDGE, POS_SUBPLOT_BOTTOM_EDGE,
	POS_SUBPLOT_LEFT_EDGE, POS_SUBPLOT_RIGHT_EDGE,
	POS_SUBPLOT_HSPACE, POS_SUBPLOT_WSPACE, SHOW_LEGEND,
	ERROR_NO_DATA_MATCH, PERCENTILE_BY_ID
)
from src.parsing.log_parser import get_region_locations
from src.plotting.configs import MK_CONFIG, CM_CONFIG, REGIONAL_CONFIG
from src.widgets.custom_combobox import RightClickableComboBox

STR_START_MOMENT = "Start"
STR_END_MOMENT = "End"

# Reference bands by ID
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

# Classic-mode outer envelope, first available pair wins
STATS_OUTER_COLOR = "#2e7d32"
STATS_OUTER_ALPHA = 0.04
STATS_OUTER_PAIRS = [
	("Minimum", "Maximum"),
	("Extremely low (1st)", "Extremely high (99th)"),
	("Very low (5th)", "Very high (95th)"),
]
MARGIN_BETWEEN_BORDERS_AND_OUTER_DATA_POINTS = 0

def _draw_horizontal_axis(ax):
	"""Draws horizontal grid lines after every number on the y-axis and a zero line."""
	ax.spines['bottom'].set_visible(True)
	ax.set_axisbelow(True)
	# Horizontal line across every number on the left (y) axis
	ax.yaxis.grid(True, linestyle='--', linewidth=0.7, color='#cccccc', alpha=0.7)

	y_min, y_max = ax.get_ylim()
	if y_min <= 0 <= y_max:
		linestyle = '--' if (y_min < 0 and y_max > 0) else '-'
		ax.axhline(0, color='#666666', linewidth=0.8, linestyle=linestyle, alpha=0.75, zorder=1)


def _create_generic_graph(
	data,
	ax,
	filter_layout,
	filter_widgets_list,
	on_lines_plotted,
	on_plot_cleared,
	filter_widget_map,
	get_is_moving_avg,
	get_period_value,
	get_is_stats_mode=lambda: False,
	on_stats_computed=None,
	get_stats_bands=lambda: 9,
	set_redraw_fn=None,
	get_density_mode=lambda: "none",
	get_stats_hide_level=lambda: 0,
	get_stats_shading_all=lambda: False,
	get_is_year_offset=lambda: False,
	get_derivative_order=lambda: 0,
	get_is_ratio_mode=lambda: False,
	get_is_bar_chart=lambda: False,
	*,
	config
):
	all_data = config["parser"](data)
	fig = ax.figure
	fig.subplots_adjust(
		top=POS_SUBPLOT_TOP_EDGE,
		bottom=POS_SUBPLOT_BOTTOM_EDGE,
		left=POS_SUBPLOT_LEFT_EDGE,
		right=POS_SUBPLOT_RIGHT_EDGE,
		hspace=POS_SUBPLOT_HSPACE,
		wspace=POS_SUBPLOT_WSPACE
	)

	category_key = config["category_key"]
	value_key = config["value_key"]
	category_label_str = config["category_label"]
	all_category_str = config["all_category_str"]
	value_label_str = config["value_label"]
	add_zero_start = config.get("add_zero_start", False)
	has_region = config.get("has_region_filter", True)
	entity_key = config.get("entity_key", "region")
	region_label_str = config.get("region_label", "Region:")
	all_region_str = config.get("all_region_str", STR_ALL_REGIONS)

	is_year_offset = get_is_year_offset()
	ax._is_year_offset = is_year_offset

	all_moments = sorted(list(set(item['moment'] for item in all_data)))

	# Time, From, To, Metric, Region/Country ---
	time_label_text = "View year:"
	lbl_moment = QLabel(time_label_text)
	combo_moment = RightClickableComboBox()
	combo_moment._last_offset_state = is_year_offset
	combo_moment.addItem(STR_ALL_MOMENTS, userData=None)
	for m in all_moments:
		lbl = str(m - 1337) if is_year_offset else str(m)
		combo_moment.addItem(lbl, userData=m)
	filter_widget_map['moment'] = combo_moment
	filter_widget_map['lbl_moment'] = lbl_moment

	lbl_from = QLabel("Year start:")
	combo_from = RightClickableComboBox()
	combo_from._last_offset_state = is_year_offset
	combo_from.addItem(STR_START_MOMENT, userData=None)
	for m in all_moments:
		lbl = str(m - 1337) if is_year_offset else str(m)
		combo_from.addItem(lbl, userData=m)
	filter_widget_map['from_year'] = combo_from
	filter_widget_map['lbl_from_year'] = lbl_from

	lbl_to = QLabel("Year end:")
	combo_to = RightClickableComboBox()
	combo_to._last_offset_state = is_year_offset
	combo_to.addItem(STR_END_MOMENT, userData=None)
	for m in all_moments:
		lbl = str(m - 1337) if is_year_offset else str(m)
		combo_to.addItem(lbl, userData=m)
	filter_widget_map['to_year'] = combo_to
	filter_widget_map['lbl_to_year'] = lbl_to

	# Apply initial visibility according to bar chart mode
	is_bar_mode = get_is_bar_chart()
	lbl_moment.setVisible(is_bar_mode)
	combo_moment.setVisible(is_bar_mode)
	lbl_from.setVisible(not is_bar_mode)
	combo_from.setVisible(not is_bar_mode)
	lbl_to.setVisible(not is_bar_mode)
	combo_to.setVisible(not is_bar_mode)
	if is_bar_mode and combo_moment.count() > 1:
		combo_moment.setCurrentIndex(combo_moment.count() - 1)

	# Category / Metric dropdown
	lbl_category = QLabel(category_label_str)
	combo_category = RightClickableComboBox()
	all_categories = sorted(list(set(item[category_key] for item in all_data)))
	if all_category_str:
		combo_category.addItem(all_category_str)
	combo_category.addItems(all_categories)
	filter_widget_map[category_key] = combo_category

	filter_layout.addWidget(lbl_moment, 0, 0)
	filter_layout.addWidget(combo_moment, 0, 1)
	filter_layout.addWidget(lbl_from, 0, 2)
	filter_layout.addWidget(combo_from, 0, 3)
	filter_layout.addWidget(lbl_to, 0, 4)
	filter_layout.addWidget(combo_to, 0, 5)
	filter_layout.addWidget(lbl_category, 0, 6)
	filter_layout.addWidget(combo_category, 0, 7)
	filter_widgets_list.extend([lbl_moment, combo_moment, lbl_from, combo_from, lbl_to, combo_to, lbl_category, combo_category])

	# Region / Country / Market dropdown
	combo_region = None
	if has_region:
		lbl_region = QLabel(region_label_str)
		combo_region = RightClickableComboBox()
		all_entities = sorted(list(set(
			item.get(entity_key) or item.get('country') or item.get('region', '')
			for item in all_data
			if (item.get(entity_key) or item.get('country') or item.get('region', ''))
		)))
		combo_region.addItem(all_region_str)
		combo_region.addItems(all_entities)
		filter_widget_map[entity_key] = combo_region

		filter_layout.addWidget(lbl_region, 0, 8)
		filter_layout.addWidget(combo_region, 0, 9)
		filter_layout.setColumnStretch(10, 1)
		filter_widgets_list.extend([lbl_region, combo_region])
	else:
		filter_layout.setColumnStretch(8, 1)

	def _sync_combo_years(combo, default_text):
		is_yr_offset = get_is_year_offset()
		if getattr(combo, '_last_offset_state', None) != is_yr_offset:
			combo._last_offset_state = is_yr_offset
			cur_data = combo.currentData()
			combo.blockSignals(True)
			combo.clear()
			combo.addItem(default_text, userData=None)
			for m in all_moments:
				lbl = str(m - 1337) if is_yr_offset else str(m)
				combo.addItem(lbl, userData=m)
			if cur_data is not None:
				idx = combo.findData(cur_data)
				combo.setCurrentIndex(idx if idx != -1 else 0)
			else:
				combo.setCurrentIndex(0)
			combo.blockSignals(False)

	def update_plot():
		on_plot_cleared()
		ax.clear()

		is_yr_offset = get_is_year_offset()
		ax._is_year_offset = is_yr_offset

		# Refresh year dropdown labels when offset toggles
		lbl_moment.setText("View Year:")
		_sync_combo_years(combo_moment, STR_ALL_MOMENTS)
		_sync_combo_years(combo_from, STR_START_MOMENT)
		_sync_combo_years(combo_to, STR_END_MOMENT)

		m_filter = combo_moment.currentText()
		selected_moment = combo_moment.currentData()
		c_filter = combo_category.currentText()
		r_filter = combo_region.currentText() if combo_region else all_region_str

		from_moment = combo_from.currentData()
		to_moment = combo_to.currentData()

		if has_region and all_category_str and c_filter != all_category_str and r_filter != all_region_str:
			ax.text(0.5, 0.5, f"Please select a specific {category_label_str.replace(':', '')} OR a {region_label_str.replace(':', '')}, not both.",
					ha='center', va='center')
			ax.figure.canvas.draw_idle()
			return

		# Base filter
		pre_filtered = [
			item for item in all_data
			if (selected_moment is None or item['moment'] == selected_moment) and
			   (from_moment is None or item['moment'] >= from_moment) and
			   (to_moment is None or item['moment'] <= to_moment) and
			   (c_filter == all_category_str or c_filter == item.get(category_key)) and
			   (r_filter == all_region_str or r_filter == (item.get(entity_key) or item.get('country') or item.get('region')))
		]
		filtered = [i for i in pre_filtered if i[value_key] != 0] if config.get("ignore_zeros") else pre_filtered

		if not filtered:
			ax.text(0.5, 0.5, ERROR_NO_DATA_MATCH, ha='center', va='center')
			ax.figure.canvas.draw_idle()
			if on_stats_computed:
				on_stats_computed(None)
			return

		density_mode = get_density_mode()
		deriv_order = get_derivative_order()
		is_ratio_mode = get_is_ratio_mode() and (selected_moment is None)
		base_year_disp = None
		effective_val_label = value_label_str

		# Density Transformation
		if density_mode == "location":
			effective_val_label = f"{effective_val_label} / Location"
			rloc_map = get_region_locations()
			has_valid_locations = False
			transformed = []
			for itm in filtered:
				copy_item = dict(itm)
				locs = 0.0
				if "locations" in copy_item and (copy_item.get("locations") or 0) > 0:
					locs = float(copy_item["locations"])
					has_valid_locations = True
				else:
					reg = copy_item.get("region", "")
					locs = float(rloc_map.get(reg, 0))
					if locs > 0:
						has_valid_locations = True
				copy_item[value_key] = (copy_item[value_key] / locs) if locs > 0 else 0.0
				transformed.append(copy_item)

			if not has_valid_locations:
				ax.text(0.5, 0.5, "No count of locations stored for this data.\nCannot calculate density by location.",
						ha='center', va='center', fontsize=12, color='red')
				ax.figure.canvas.draw_idle()
				if on_stats_computed:
					on_stats_computed(None)
				return
			filtered = transformed

		elif density_mode == "population":
			effective_val_label = f"{effective_val_label} / 1M Pop"
			has_valid_population = False
			transformed = []
			for itm in filtered:
				copy_item = dict(itm)
				pop = copy_item.get("population") or copy_item.get("total_population") or copy_item.get("Population") or 0.0
				try: pop = float(pop)
				except (ValueError, TypeError): pop = 0.0

				if pop > 0:
					has_valid_population = True
					copy_item[value_key] = (copy_item[value_key] / pop) * 1_000_000.0
				else:
					copy_item[value_key] = 0.0
				transformed.append(copy_item)

			if not has_valid_population:
				ax.text(0.5, 0.5, "No population stored for this data.\nCannot calculate density by population.",
						ha='center', va='center', fontsize=12, color='red')
				ax.figure.canvas.draw_idle()
				if on_stats_computed:
					on_stats_computed(None)
				return

			filtered = transformed

		# Ratio / Indexation Transformation (100% at base year)
		if is_ratio_mode:
			# Base year is from_moment if picked; otherwise the earliest available year in filtered data
			all_filt_moments = sorted(set(i['moment'] for i in filtered))
			base_year = from_moment if (from_moment is not None and from_moment in all_filt_moments) else (all_filt_moments[0] if all_filt_moments else None)

			if base_year is not None:
				base_year_disp = str(base_year - 1337) if is_yr_offset else str(base_year)
				effective_val_label = f"% of Year {base_year_disp}"

				# Collect baseline values for each (entity, category) pair at base_year
				base_lookup = {}
				for itm in filtered:
					if itm['moment'] == base_year:
						ent = itm.get(entity_key, itm.get('country', itm.get('region', '')))
						cat = itm.get(category_key, '')
						base_lookup[(ent, cat)] = float(itm[value_key])

				ratio_transformed = []
				for itm in filtered:
					ent = itm.get(entity_key, itm.get('country', itm.get('region', '')))
					cat = itm.get(category_key, '')
					base_val = base_lookup.get((ent, cat))

					# Exclude entities that had 0 or missing baseline value
					if base_val is None or base_val <= 0:
						continue

					copy_item = dict(itm)
					copy_item[value_key] = ((float(itm[value_key]) / base_val) - 1.0) * 100.0
					ratio_transformed.append(copy_item)

				filtered = ratio_transformed

		# Derivative Transformation (Rate or Acceleration)
		if deriv_order > 0:
			if deriv_order == 1:
				effective_val_label = f"Δ {effective_val_label} / Year"
			elif deriv_order == 2:
				effective_val_label = f"Δ² {effective_val_label} / Year²"

			deriv_transformed = []
			entity_series_map = {}
			for item in filtered:
				ent = item.get(entity_key, item.get('country', item.get('region', '')))
				# Distinguish metrics when plotting multiple metrics in a region
				c_val = item.get(category_key, '')
				key = (ent, c_val)
				entity_series_map.setdefault(key, []).append(dict(item))

			for key, series_items in entity_series_map.items():
				series_items.sort(key=lambda x: x['moment'])
				if deriv_order == 1:
					for i in range(1, len(series_items)):
						diff_item = dict(series_items[i])
						diff_item[value_key] = series_items[i][value_key] - series_items[i - 1][value_key]
						deriv_transformed.append(diff_item)
				elif deriv_order == 2:
					for i in range(2, len(series_items)):
						accel_item = dict(series_items[i])
						d_curr = series_items[i][value_key] - series_items[i - 1][value_key]
						d_prev = series_items[i - 1][value_key] - series_items[i - 2][value_key]
						accel_item[value_key] = d_curr - d_prev
						deriv_transformed.append(accel_item)

			if not deriv_transformed:
				needed = 2 if deriv_order == 1 else 3
				d_term = "rate (Δ)" if deriv_order == 1 else "acceleration (Δ²)"
				ax.text(0.5, 0.5, f"Need at least {needed} consecutive time steps to calculate {d_term}.",
						ha='center', va='center', fontsize=12)
				ax.figure.canvas.draw_idle()
				if on_stats_computed:
					on_stats_computed(None)
				return

			filtered = deriv_transformed

		is_r_picked = (r_filter != all_region_str)
		display_title = f"{c_filter} in {r_filter}" if (is_r_picked and not all_category_str) else (r_filter if is_r_picked else c_filter)

		if get_is_stats_mode() and selected_moment is None and not is_r_picked:
			_render_stats_mode(ax, filtered, value_key, effective_val_label, display_title, entity_key,
							   get_stats_hide_level(), on_stats_computed, on_lines_plotted,
							   get_is_moving_avg, get_period_value,
							   get_stats_shading_all=get_stats_shading_all,
							   is_year_offset=is_yr_offset,
							   is_ratio_mode=is_ratio_mode,
							   base_year_disp=base_year_disp)
			return

		_render_standard_mode(ax, filtered, m_filter, c_filter, r_filter, all_category_str,
							  category_key, value_key, effective_val_label, add_zero_start,
							  get_is_moving_avg, get_period_value, config, on_stats_computed, on_lines_plotted,
							  entity_key=entity_key, all_region_str=all_region_str,
							  is_year_offset=is_yr_offset,
							  is_ratio_mode=is_ratio_mode,
							  base_year_disp=base_year_disp)

	if set_redraw_fn:
		set_redraw_fn(update_plot)

	combo_moment.currentIndexChanged.connect(update_plot)
	combo_category.currentIndexChanged.connect(update_plot)
	combo_from.currentIndexChanged.connect(update_plot)
	combo_to.currentIndexChanged.connect(update_plot)
	if combo_region:
		combo_region.currentIndexChanged.connect(update_plot)
	update_plot()

def _calculate_series_stats(country_series, all_values, value_label):
	"""Helper to calculate consecutive deltas, overall deltas, volatility, and summary metrics."""
	consecutive_changes = []
	overall_changes = []
	entity_volatilities = []

	for ent, history in country_series.items():
		vals = list(history.values())
		if len(vals) >= 2:
			h_sorted = sorted(history.keys())
			entity_volatilities.append((
				ent,
				float(np.std(vals)),
				h_sorted[0],
				h_sorted[-1]
			))
			# Consecutive step deltas
			for i in range(len(h_sorted) - 1):
				y_from, y_to = h_sorted[i], h_sorted[i + 1]
				v_from, v_to = history[y_from], history[y_to]
				if v_from != 0 and v_to != 0:
					delta = v_to - v_from
					consecutive_changes.append((ent, delta, v_from, v_to, y_from, y_to))

			# Non-consecutive: find maximum rise and fall across all chronological pairs
			max_pos_delta = 0
			best_pos_pair = None
			max_neg_delta = 0
			best_neg_pair = None

			for i in range(len(h_sorted)):
				for j in range(i + 1, len(h_sorted)):
					y_i, y_j = h_sorted[i], h_sorted[j]
					v_i, v_j = history[y_i], history[y_j]
					if v_i == 0 or v_j == 0:
						continue
					d = v_j - v_i
					if d > max_pos_delta:
						max_pos_delta = d
						best_pos_pair = (ent, d, v_i, v_j, y_i, y_j)
					elif d < max_neg_delta:
						max_neg_delta = d
						best_neg_pair = (ent, d, v_i, v_j, y_i, y_j)

			if best_pos_pair:
				overall_changes.append(best_pos_pair)
			if best_neg_pair:
				overall_changes.append(best_neg_pair)

	return {
		"value_label": value_label,
		"biggest_increase": sorted(consecutive_changes, key=lambda x: x[1], reverse=True)[:5],
		"biggest_decrease": sorted(consecutive_changes, key=lambda x: x[1])[:5],
		"overall_increase": sorted([c for c in overall_changes if c[1] > 0], key=lambda x: x[1], reverse=True)[:5],
		"overall_decrease": sorted([c for c in overall_changes if c[1] < 0], key=lambda x: x[1])[:5],
		"most_volatile": sorted(entity_volatilities, key=lambda x: x[1], reverse=True)[:5],
		"overall_mean": float(np.mean(all_values)) if all_values else 0.0,
		"overall_std": float(np.std(all_values)) if all_values else 0.0
	}


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
			if p == 100: stat_curves[s_id].append(vals[-1])
			elif p == 0: stat_curves[s_id].append(vals[0])
			elif p == 50: stat_curves[s_id].append(float(np.median(vals)))
			else: stat_curves[s_id].append(float(np.percentile(vals, p)))

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

	# Calculate statistical summaries for standard mode as well
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

		title_prefix = f"Relative change from time {base_year_disp}" if (is_ratio_mode and base_year_disp) else f"{val_label}s"

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
			if is_ma and len(sv) > 1:
				ma_vals = [sum(sv[max(0, i-p+1):i+1]) / len(sv[max(0, i-p+1):i+1]) for i in range(len(sv))]
				ax.plot(sm, ma_vals, linestyle='-', label=name, color=next(colors))
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
		ax.set_title(f"{val_label}s for {time_display}")
		plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

		if items:
			patches = [mpatches.Patch(color=c, label=l) for l, c in cmap.items()]
			ax.legend(handles=patches, bbox_to_anchor=(1.04, 1), loc="upper left")
	else:
		ax.text(0.5, 0.5, "Please select a filter to display a graph.", ha='center', va='center')

	_draw_horizontal_axis(ax)
	ax.figure.canvas.draw_idle()
	on_lines_plotted()

# --- Chart entry wrappers ---
def graph_country_metrics(*args, **kwargs):
	"""Country Metrics (combined Country & Credit statistics)"""
	kwargs["config"] = CM_CONFIG
	_create_generic_graph(*args, **kwargs)

def graph_markets(*args, **kwargs):
	"""Market Statistics"""
	kwargs["config"] = MK_CONFIG
	_create_generic_graph(*args, **kwargs)

def graph_regional_statistics(*args, **kwargs):
	"""Regional Statistics (combined Buildings, Goods Prices, Population, Road Coverages)"""
	kwargs["config"] = REGIONAL_CONFIG
	_create_generic_graph(*args, **kwargs)