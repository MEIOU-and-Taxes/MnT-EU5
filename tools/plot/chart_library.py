from itertools import cycle

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from PyQt6.QtWidgets import QLabel, QComboBox

from tools.plot.custom_widgets import RightClickableComboBox
from tools.plot.log_parser import parse_data_goods_prices, parse_data_building_types, parse_data_population

FIRST_MONTH = 5 # Makes FIRST_MONTH-1 not have 0 buildings in all regions

STR_ALL_MONTHS = "All months"
STR_ALL_BUILDINGS = "All buildings"
STR_ALL_REGIONS = "All regions"
STR_ALL_GOODS = "All goods"

POS_SUBPLOT_BOTTOM_EDGE = 0.10
POS_SUBPLOT_RIGHT_EDGE = 0.95
SHOW_LEGEND = False

# This function will be monkey-patched by the main script
def get_data(data, str_target):
	raise NotImplementedError("get_data function was not assigned")


def _create_generic_graph(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, config):
	"""
	A generic graphing function that creates a line or bar chart based on a configuration.
	This function is intended for internal use and is called by specific graph functions.
	"""
	all_data = config["parser"](data)
	fig = ax.figure
	fig.subplots_adjust(bottom=POS_SUBPLOT_BOTTOM_EDGE, right=POS_SUBPLOT_RIGHT_EDGE)

	# --- Get config values ---
	category_key = config["category_key"]
	value_key = config["value_key"]
	category_label_str = config["category_label"]
	all_category_str = config["all_category_str"]
	value_label_str = config["value_label"]
	add_zero_start = config.get("add_zero_start", False)
	ComboBoxClass = RightClickableComboBox if config.get("use_right_click_combo", True) else QComboBox

	# --- Create Interactive PyQt Widgets ---
	lbl_month = QLabel("Month:")
	combo_month = ComboBoxClass()
	all_months = sorted(list(set(item['month'] for item in all_data)))
	combo_month.addItem(STR_ALL_MONTHS)
	combo_month.addItems([str(m) for m in all_months])

	lbl_category = QLabel(category_label_str)
	combo_category = ComboBoxClass()
	all_categories = sorted(list(set(item[category_key] for item in all_data)))
	combo_category.addItem(all_category_str)
	combo_category.addItems(all_categories)

	lbl_region = QLabel("Region:")
	combo_region = ComboBoxClass()
	all_regions = sorted(list(set(item['region'] for item in all_data)))
	combo_region.addItem(STR_ALL_REGIONS)
	combo_region.addItems(all_regions)

	# Add widgets to the layout
	filter_layout.addWidget(lbl_month, 0, 0)
	filter_layout.addWidget(combo_month, 0, 1)
	filter_layout.addWidget(lbl_category, 0, 2)
	filter_layout.addWidget(combo_category, 0, 3)
	filter_layout.addWidget(lbl_region, 0, 4)
	filter_layout.addWidget(combo_region, 0, 5)
	filter_layout.setColumnStretch(6, 1)

	filter_widgets_list.extend([lbl_month, combo_month, lbl_category, combo_category, lbl_region, combo_region])

	def update_plot():
		on_plot_cleared()
		filter_month_str = combo_month.currentText()
		filter_category_type = combo_category.currentText()
		filter_region = combo_region.currentText()
		ax.clear()

		if filter_category_type != all_category_str and filter_region != STR_ALL_REGIONS:
			ax.text(0.5, 0.5, f"Please select a specific {category_label_str.replace(':', '')} OR a Region, not both.",
					ha='center', va='center')
			ax.figure.canvas.draw_idle()
			return

		filtered_data = [
			item for item in all_data
			if (filter_month_str == STR_ALL_MONTHS or item['month'] == int(filter_month_str)) and
			   (filter_category_type == all_category_str or filter_category_type == item[category_key]) and
			   (filter_region == STR_ALL_REGIONS or filter_region == item['region'])
		]

		if not filtered_data:
			ax.text(0.5, 0.5, "No data matches the current filters.", ha='center', va='center')
			ax.figure.canvas.draw_idle()
			return

		is_month_all = filter_month_str == STR_ALL_MONTHS
		is_category_picked = filter_category_type != all_category_str
		is_region_picked = filter_region != STR_ALL_REGIONS
		prop_cycle = plt.rcParams['axes.prop_cycle']
		colors = cycle(prop_cycle.by_key()['color'])

		# --- Line Graph Logic ---
		if is_month_all and (is_category_picked or is_region_picked):
			plot_category_key = category_key if is_region_picked else 'region'
			data_to_plot = {}
			for item in filtered_data:
				key = item[plot_category_key]
				if key not in data_to_plot:
					data_to_plot[key] = {'months': [], 'values': []}
				data_to_plot[key]['months'].append(item['month'])
				data_to_plot[key]['values'].append(item[value_key])

			if add_zero_start:
				for _, values in data_to_plot.items():
					if not values['months']: continue
					min_month = min(values['months'])
					if min_month != FIRST_MONTH:
						values['months'].append(min_month - 1)
						values['values'].append(0)

			ax.set_xlabel("Month")
			ax.set_ylabel(value_label_str)
			title_text = f"{value_label_str}s for: {filter_category_type}" if is_category_picked else f"{value_label_str}s in: {filter_region}"
			ax.set_title(title_text)

			for name, values in sorted(data_to_plot.items()):
				if not values['months']: continue
				sorted_points = sorted(zip(values['months'], values['values']))
				months_sorted, values_sorted = zip(*sorted_points)
				ax.plot(months_sorted, values_sorted, marker='o', linestyle='-', label=name, color=next(colors))

			if data_to_plot:
				min_x = min(min(v['months']) for v in data_to_plot.values() if v['months'])
				max_x = max(max(v['months']) for v in data_to_plot.values() if v['months'])
				ax.set_xlim(min_x, max_x)

			if SHOW_LEGEND and data_to_plot:
				ax.legend(bbox_to_anchor=(1.04, 1), loc="upper left")
			ax.figure.canvas.draw_idle()
			on_lines_plotted()

		# --- Bar Graph Logic ---
		elif not is_month_all and (is_category_picked or is_region_picked):
			coloring_key = category_key if is_region_picked else 'region'
			unique_items = sorted(list(set(item[coloring_key] for item in filtered_data)))
			color_map = {name: next(colors) for name in unique_items}
			labels = [f"{item[category_key]}\n({item['region']})" for item in filtered_data]
			values = [item[value_key] for item in filtered_data]
			bar_colors = [color_map[item[coloring_key]] for item in filtered_data]

			ax.bar(labels, values, color=bar_colors)
			ax.set_ylabel(value_label_str)
			ax.set_title(f"{value_label_str}s for Month: {filter_month_str}")
			plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

			if unique_items:
				patches = [mpatches.Patch(color=c, label=l) for l, c in color_map.items()]
				ax.legend(handles=patches, bbox_to_anchor=(1.04, 1), loc="upper left")
			ax.figure.canvas.draw_idle()
		else:
			ax.text(0.5, 0.5, "Please select a filter to display a graph.", ha='center', va='center')
		ax.figure.canvas.draw_idle()

	combo_month.currentIndexChanged.connect(update_plot)
	combo_category.currentIndexChanged.connect(update_plot)
	combo_region.currentIndexChanged.connect(update_plot)
	update_plot()


def graph_population(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared):
	"""Population by Region"""
	all_pop_data = parse_data_population(data)
	fig = ax.figure
	fig.subplots_adjust(bottom=POS_SUBPLOT_BOTTOM_EDGE, right=POS_SUBPLOT_RIGHT_EDGE)

	# --- Create Interactive PyQt Widgets ---
	lbl_region = QLabel("Region:")
	combo_region = RightClickableComboBox()
	all_regions = sorted(list(set(item['region'] for item in all_pop_data)))
	combo_region.addItem(STR_ALL_REGIONS)
	combo_region.addItems(all_regions)

	# Add widgets to the layout
	filter_layout.addWidget(lbl_region, 0, 0)
	filter_layout.addWidget(combo_region, 0, 1)
	filter_layout.setColumnStretch(2, 1)

	filter_widgets_list.extend([lbl_region, combo_region])

	def update_plot():
		on_plot_cleared()
		filter_region = combo_region.currentText()
		ax.clear()

		filtered_data = [
			item for item in all_pop_data
			if (filter_region == STR_ALL_REGIONS or item['region'] == filter_region)
		]

		if not filtered_data:
			ax.text(0.5, 0.5, "No data matches the current filters.", ha='center', va='center')
			ax.figure.canvas.draw_idle()
			return

		# --- Plotting Logic ---
		prop_cycle = plt.rcParams['axes.prop_cycle']
		colors = cycle(prop_cycle.by_key()['color'])

		data_to_plot = {}
		for item in filtered_data:
			key = item['region']
			if key not in data_to_plot:
				data_to_plot[key] = {'months': [], 'populations': []}
			data_to_plot[key]['months'].append(item['month'])
			data_to_plot[key]['populations'].append(item['population'])

		ax.set_xlabel("Month")
		ax.set_ylabel("Population")
		ax.set_title("Population Over Time")

		for name, values in sorted(data_to_plot.items()):
			if not values['months']: continue
			sorted_points = sorted(zip(values['months'], values['populations']))
			months_sorted, pop_sorted = zip(*sorted_points)
			ax.plot(months_sorted, pop_sorted, marker='o', linestyle='-', label=name, color=next(colors))

		if data_to_plot:
			min_x = min(min(v['months']) for v in data_to_plot.values() if v['months'])
			max_x = max(max(v['months']) for v in data_to_plot.values() if v['months'])
			ax.set_xlim(min_x, max_x)

		if SHOW_LEGEND and data_to_plot:
			ax.legend(bbox_to_anchor=(1.04, 1), loc="upper left")

		ax.figure.canvas.draw_idle()
		on_lines_plotted()

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
    "use_right_click_combo": True
}

GP_CONFIG = {
    "parser": parse_data_goods_prices,
    "category_key": "good",
    "value_key": "price",
    "category_label": "Good:",
    "all_category_str": STR_ALL_GOODS,
    "value_label": "Price",
    "add_zero_start": False,
    "use_right_click_combo": True
}

# --- Public Graphing Functions ---

def graph_building_types(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared):
	"""Building Types by Region"""
	_create_generic_graph(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, config=BT_CONFIG)

def graph_goods_prices(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared):
	"""Goods Prices by Region"""
	_create_generic_graph(data, ax, filter_layout, filter_widgets_list, on_lines_plotted, on_plot_cleared, config=GP_CONFIG)


if __name__ == "__main__":
	print("This file contains graphing functions and is not meant to be run directly.")
	print("Please run MT_grapher.py instead.")