from itertools import cycle

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from PyQt6.QtWidgets import QLabel, QComboBox

from tools.plot.MT_grapher import is_path_found, ERROR_FILE_NOT_FOUND
from tools.plot.custom_widgets import RightClickableComboBox
from tools.plot.log_parser import parse_data_goods_prices, parse_data_building_types, parse_data_population, \
	parse_data_markets, parse_data_road_types
from matplotlib.ticker import MaxNLocator

IS_LOGGING_YEARLY = True
FIRST_MOMENT = 1 + 1337 if IS_LOGGING_YEARLY else 4 # Makes FIRST_MOMENT-1 not have 0 buildings in all regions

STR_ALL_MOMENTS = "All moments"
STR_ALL_BUILDINGS = "All buildings"
STR_ALL_REGIONS = "All regions"
STR_ALL_GOODS = "All goods"
STR_ALL_ROAD_TYPES = "All road types"

ERROR_NO_DATA_MATCH = "No data matches the current filters"
ERROR_NO_STATISTICS = "The logs exist, but there are no statistics stored\nPlay more or get other logs"

POS_SUBPLOT_BOTTOM_EDGE = 0.10
POS_SUBPLOT_RIGHT_EDGE = 0.95
SHOW_LEGEND = False
has_found_statistics = False

# This function will be monkey-patched by the main script
def get_data(data, str_target):
	raise NotImplementedError("get_data function was not assigned")


def _create_generic_graph(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, config, filter_widget_map, get_is_moving_avg, get_period_value):
	"""
	A generic graphing function that creates a line or bar chart based on a configuration.
	This function is intended for internal use and is called by specific graph functions.
	"""
	all_data = config["parser"](data)
	fig = ax.figure
	fig.subplots_adjust(bottom=POS_SUBPLOT_BOTTOM_EDGE, right=POS_SUBPLOT_RIGHT_EDGE)

	# --- Get config values ---
	# Key name, used for grouping, primary filtering & creating lines. It's the main thing to analyze in the chart
	category_key = config["category_key"]
	# Numerical value to plot
	value_key = config["value_key"]
	# Label for the category dropdown menu
	category_label_str = config["category_label"]
	# The default "show everything" option appearing at the top of the category dropdown
	all_category_str = config["all_category_str"]
	# Label for the graph's Y axis
	value_label_str = config["value_label"]
	# Boolean controlling whether it will create a moment having values of 0 before the moment it *has* values
	add_zero_start = config.get("add_zero_start", False)

	# --- Create Interactive PyQt Widgets ---
	lbl_moment = QLabel("Time:")
	ComboBoxClass = RightClickableComboBox
	combo_moment = ComboBoxClass()
	all_moments = sorted(list(set(item['moment'] for item in all_data)))
	combo_moment.addItem(STR_ALL_MOMENTS)
	combo_moment.addItems([str(m) for m in all_moments])
	filter_widget_map['moment'] = combo_moment

	lbl_category = QLabel(category_label_str)
	combo_category = ComboBoxClass()
	all_categories = sorted(list(set(item[category_key] for item in all_data)))
	if all_category_str:
		combo_category.addItem(all_category_str)
	combo_category.addItems(all_categories)
	filter_widget_map[category_key] = combo_category

	is_market_chart = 'Food Stockpile' in all_categories
	is_road_chart = category_key == 'road_type'

	lbl_region = QLabel("Region:")
	combo_region = ComboBoxClass()
	all_regions = sorted(list(set(item['region'] for item in all_data)))
	combo_region.addItem(STR_ALL_REGIONS)
	combo_region.addItems(all_regions)
	filter_widget_map['region'] = combo_region

	if is_market_chart or is_road_chart:
		lbl_moment.setVisible(False)
		combo_moment.setVisible(False)
	if is_market_chart:
		lbl_region.setVisible(False)
		combo_region.setVisible(False)

	# Add widgets to the layout
	filter_layout.addWidget(lbl_moment, 0, 0)
	filter_layout.addWidget(combo_moment, 0, 1)
	filter_layout.addWidget(lbl_category, 0, 2)
	filter_layout.addWidget(combo_category, 0, 3)
	filter_layout.addWidget(lbl_region, 0, 4)
	filter_layout.addWidget(combo_region, 0, 5)
	filter_layout.setColumnStretch(6, 1)

	widgets = [lbl_moment, combo_moment, lbl_category, combo_category]
	widgets.extend([lbl_region, combo_region])
	filter_widgets_list.extend(widgets)

	def update_plot():
		on_plot_cleared()
		filter_moment_str = combo_moment.currentText()
		filter_category_type = combo_category.currentText()
		filter_region = combo_region.currentText()
		ax.clear()

		if filter_category_type != all_category_str and filter_region != STR_ALL_REGIONS:
			ax.text(0.5, 0.5, f"Please select a specific {category_label_str.replace(':', '')} OR a Region, not both.",
					ha='center', va='center')
			ax.figure.canvas.draw_idle()
			return

		pre_filtered_data = [
			item for item in all_data
			if (filter_moment_str == STR_ALL_MOMENTS or item['moment'] == int(filter_moment_str)) and
			   (filter_category_type == all_category_str or filter_category_type == item[category_key]) and
			   (filter_region == STR_ALL_REGIONS or filter_region == item['region'])
		]

		if config.get("ignore_zeros", False):
			filtered_data = [item for item in pre_filtered_data if item[value_key] != 0]
		else:
			filtered_data = pre_filtered_data

		if not filtered_data:
			ax.text(0.5, 0.5, get_error_message(), ha='center', va='center')
			ax.figure.canvas.draw_idle()
			return

		is_moment_all = filter_moment_str == STR_ALL_MOMENTS
		is_category_picked = filter_category_type != all_category_str
		is_region_picked = filter_region != STR_ALL_REGIONS
		prop_cycle = plt.rcParams['axes.prop_cycle']
		colors = cycle(prop_cycle.by_key()['color'])

		# --- Line Graph Logic ---
		if is_moment_all and (is_category_picked or is_region_picked):
			plot_category_key = category_key if is_region_picked else 'region'
			data_to_plot = {}
			for item in filtered_data:
				key = item[plot_category_key]
				if key not in data_to_plot:
					data_to_plot[key] = {'moments': [], 'values': []}
				data_to_plot[key]['moments'].append(item['moment'])
				data_to_plot[key]['values'].append(item[value_key])


			if add_zero_start and data_to_plot:
				# First, find the earliest moment across ALL lines being plotted.
				all_moments = [moment for v in data_to_plot.values() for moment in v['moments']]
				if not all_moments: return # Should not happen if data_to_plot is not empty, but safe to have

				overall_min_moment = min(all_moments)

				# Now, add a zero-point only if a line starts AFTER that earliest moment.
				for _, values in data_to_plot.items():
					if not values['moments']: continue

					line_min_moment = min(values['moments'])
					if line_min_moment > overall_min_moment:
						values['moments'].append(line_min_moment - 1)
						values['values'].append(0)

			ax.set_xlabel("Time")
			ax.xaxis.set_major_locator(MaxNLocator(integer=True))
			ax.set_ylabel(value_label_str)
			title_text = f"{value_label_str}s for: {filter_category_type}" if is_category_picked else f"{value_label_str}s in: {filter_region}"
			ax.set_title(title_text)

			unique_moments_count = len(set(item['moment'] for item in filtered_data))
			marker_style = 'o' if unique_moments_count <= 50 else None

			is_moving_average = get_is_moving_avg()

			for name, values in sorted(data_to_plot.items()):
				if not values['moments']: continue
				sorted_points = sorted(zip(values['moments'], values['values']))
				moments_sorted, values_sorted = zip(*sorted_points)

				if is_moving_average and len(values_sorted) > 1:
					period = get_period_value()
					moving_avg_values = []
					for i in range(len(values_sorted)):
						current_window_size = min(i + 1, period)
						window = values_sorted[i - current_window_size + 1 : i + 1]
						moving_avg_values.append(sum(window) / len(window))
					ax.plot(moments_sorted, moving_avg_values, marker=None, linestyle='-', label=name, color=next(colors))
				else:
					ax.plot(moments_sorted, values_sorted, marker=marker_style, linestyle='-', label=name, color=next(colors))

			if data_to_plot:
				min_x = min(min(v['moments']) for v in data_to_plot.values() if v['moments'])
				max_x = max(max(v['moments']) for v in data_to_plot.values() if v['moments'])
				ax.set_xlim(min_x, max_x)
				if "y_axis_limits" in config:
					ax.set_ylim(config["y_axis_limits"])

			if SHOW_LEGEND and data_to_plot:
				ax.legend(bbox_to_anchor=(1.04, 1), loc="upper left")
			ax.figure.canvas.draw_idle()
			on_lines_plotted()

		# --- Bar Graph Logic ---
		elif not is_moment_all and (is_category_picked or is_region_picked):
			coloring_key = category_key if is_region_picked else 'region'
			unique_items = sorted(list(set(item[coloring_key] for item in filtered_data)))
			color_map = {name: next(colors) for name in unique_items}
			if is_region_picked:
				labels = [f"{item[category_key]}" for item in filtered_data]
			elif is_category_picked:
				labels = [f"{item['region']}" for item in filtered_data]

			values = [item[value_key] for item in filtered_data]
			bar_colors = [color_map[item[coloring_key]] for item in filtered_data]

			ax.bar(labels, values, color=bar_colors)
			ax.set_ylabel(value_label_str)
			ax.set_title(f"{value_label_str}s for Month: {filter_moment_str}")
			plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

			if unique_items:
				patches = [mpatches.Patch(color=c, label=l) for l, c in color_map.items()]
				ax.legend(handles=patches, bbox_to_anchor=(1.04, 1), loc="upper left")
			ax.figure.canvas.draw_idle()
			on_lines_plotted()
		else:
			ax.text(0.5, 0.5, "Please select a filter to display a graph.", ha='center', va='center')
		ax.figure.canvas.draw_idle()

	combo_moment.currentIndexChanged.connect(update_plot)
	combo_category.currentIndexChanged.connect(update_plot)
	combo_region.currentIndexChanged.connect(update_plot)
	update_plot()


# --- Graph Configurations ---

BT_CONFIG = {
    "parser": parse_data_building_types,
    "category_key": "building",
    "value_key": "count",
    "category_label": "Building Type:",
    "all_category_str": STR_ALL_BUILDINGS,
    "value_label": "Count",
    "add_zero_start": True,
}

GP_CONFIG = {
    "parser": parse_data_goods_prices,
    "category_key": "good",
    "value_key": "price",
    "category_label": "Good:",
    "all_category_str": STR_ALL_GOODS,
    "value_label": "Price",
    "add_zero_start": False,
    "ignore_zeros": True,
}

MK_CONFIG = {
    "parser": parse_data_markets,
    "category_key": "statistic",
    "value_key": "value",
    "category_label": "Statistic:",
    "all_category_str": None,
    "value_label": "Value",
    "add_zero_start": False,
}

POP_CONFIG = {
	"parser": parse_data_population,
	"category_key": "statistic",
	"value_key": "population",
	"category_label": "Statistic:",
	"all_category_str": None,
	"value_label": "Population",
	"add_zero_start": False,
	"ignore_zeros": True,
}

RT_CONFIG = {
    "parser": parse_data_road_types,
    "category_key": "road_type",
    "value_key": "coverage_percentage",
    "category_label": "Road Type:",
    "all_category_str": STR_ALL_ROAD_TYPES,
    "value_label": "Coverage Percentage",
    "add_zero_start": True,
    "y_axis_limits": (0, 100),
}

# Functions prefixed with "graph_" are found in this module by the self.graphs code in MT_grapher.py.
# The wrapper functions are essential for this mechanism to work.
# Without them, you would need to manually create and maintain a list of all the chart configs in MT_grapher.py,
# which would be less elegant and more error-prone.
def graph_building_types(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, filter_widget_map, get_is_moving_avg, get_period_value):
	"""Building Types by Region"""
	_create_generic_graph(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, BT_CONFIG, filter_widget_map, get_is_moving_avg, get_period_value)

def graph_goods_prices(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, filter_widget_map, get_is_moving_avg, get_period_value):
	"""Goods Prices by Region"""
	_create_generic_graph(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, GP_CONFIG, filter_widget_map, get_is_moving_avg, get_period_value)

def graph_markets(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, filter_widget_map, get_is_moving_avg, get_period_value):
	"""Market Statistics"""
	_create_generic_graph(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, MK_CONFIG, filter_widget_map, get_is_moving_avg, get_period_value)

def graph_population(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, filter_widget_map, get_is_moving_avg, get_period_value):
	"""Population by Region"""
	_create_generic_graph(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, POP_CONFIG, filter_widget_map, get_is_moving_avg, get_period_value)

def graph_road_types(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, filter_widget_map, get_is_moving_avg, get_period_value):
	"""Road Coverage by Region"""
	_create_generic_graph(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, RT_CONFIG, filter_widget_map, get_is_moving_avg, get_period_value)

def get_error_message():
	if not is_path_found:
		return ERROR_FILE_NOT_FOUND
	if not has_found_statistics:
		return ERROR_NO_STATISTICS
	return ERROR_NO_DATA_MATCH

if __name__ == "__main__":
	print("This file contains graphing functions and is not meant to be run directly.")
	print("Please run MT_grapher.py instead.")