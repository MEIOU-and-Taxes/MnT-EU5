from PyQt6.QtWidgets import QLabel

from src.constants import (
	STR_ALL_MOMENTS, STR_ALL_REGIONS, POS_SUBPLOT_TOP_EDGE, POS_SUBPLOT_BOTTOM_EDGE,
	POS_SUBPLOT_LEFT_EDGE, POS_SUBPLOT_RIGHT_EDGE,
	POS_SUBPLOT_HSPACE, POS_SUBPLOT_WSPACE, ERROR_NO_DATA_MATCH
)
from src.parsing.log_parser import get_region_locations
from src.parsing.standard_renderer import _render_standard_mode
from src.plotting.configs import MK_CONFIG, CM_CONFIG, REGIONAL_CONFIG
from src.plotting.stats_renderer import _render_stats_mode
from src.widgets.custom_combobox import RightClickableComboBox

STR_START_MOMENT = "Start"
STR_END_MOMENT = "End"

STR_START_MOMENT = "Start"
STR_END_MOMENT = "End"

# Classic-mode outer envelope, first available pair wins
STATS_OUTER_PAIRS = [
	("Minimum", "Maximum"),
	("Extremely low (1st)", "Extremely high (99th)"),
	("Very low (5th)", "Very high (95th)"),
]

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
	get_baseline_mode=lambda: "none",  # "none", "ratio", "difference"
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

	# Dropdowns
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
		baseline_mode = get_baseline_mode() if selected_moment is None else "none"
		base_year_disp = None
		effective_val_label = value_label_str

		# 1. Density Transformation
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

		# 2. Baseline Transformation: Ratio (% change) or Difference (absolute delta)
		if baseline_mode in ("ratio", "difference"):
			all_filt_moments = sorted(set(i['moment'] for i in filtered))
			base_year = from_moment if (from_moment is not None and from_moment in all_filt_moments) else (all_filt_moments[0] if all_filt_moments else None)

			if base_year is not None:
				base_year_disp = str(base_year - 1337) if is_yr_offset else str(base_year)
				if baseline_mode == "ratio":
					effective_val_label = f"% of Year {base_year_disp} ({effective_val_label})"
				else:
					effective_val_label = f"Δ from Year {base_year_disp} ({effective_val_label})"

				# Collect baseline values for each (entity, category) pair at base_year
				base_lookup = {}
				for itm in filtered:
					if itm['moment'] == base_year:
						ent = itm.get(entity_key, itm.get('country', itm.get('region', '')))
						cat = itm.get(category_key, '')
						base_lookup[(ent, cat)] = float(itm[value_key])

				base_transformed = []
				for itm in filtered:
					ent = itm.get(entity_key, itm.get('country', itm.get('region', '')))
					cat = itm.get(category_key, '')
					base_val = base_lookup.get((ent, cat))

					if base_val is None:
						continue
					if baseline_mode == "ratio" and base_val == 0:
						continue

					copy_item = dict(itm)
					if baseline_mode == "ratio":
						copy_item[value_key] = ((float(itm[value_key]) / base_val) - 1.0) * 100.0
					else:
						copy_item[value_key] = float(itm[value_key]) - base_val
					base_transformed.append(copy_item)

				filtered = base_transformed

		# 3. Derivative Transformation (Rate or Acceleration)
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
							   is_ratio_mode=(baseline_mode != "none"),
							   base_year_disp=base_year_disp)
			return

		_render_standard_mode(ax, filtered, m_filter, c_filter, r_filter, all_category_str,
							  category_key, value_key, effective_val_label, add_zero_start,
							  get_is_moving_avg, get_period_value, config, on_stats_computed, on_lines_plotted,
							  entity_key=entity_key, all_region_str=all_region_str,
							  is_year_offset=is_yr_offset,
							  is_ratio_mode=(baseline_mode != "none"),
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