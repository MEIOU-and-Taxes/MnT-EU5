# Thanks to the Seelowe/Justice Fighter, the author of the code this is based on
import csv
import glob
import json
import os
import re
import sys
import traceback
from functools import partial

import matplotlib.pyplot as plt
import numpy as np
from PIL.PSDraw import ERROR_PS
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence, QIcon
from PyQt6.QtWidgets import (QApplication, QDialog, QGridLayout, QHBoxLayout,
							 QHeaderView, QMainWindow, QPushButton,
							 QTableWidget, QTableWidgetItem, QVBoxLayout,
							 QWidget, QFileDialog, QMessageBox, QComboBox, QSlider, QLabel)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

import chart_library as all_graphs
from interactive_tooltip import InteractiveLineTooltip
from tools.plot import log_parser
from tools.shared.fetch_logs import get_log_directory_from_config

TARGET_FILE_NAME_ROOT = 'error'
ERROR_FILE_NOT_FOUND = f'{TARGET_FILE_NAME_ROOT}.log not found. Please include in the config the correct path to the logs folder'
is_path_found = True
icon_path = 'icon.png'

graph_introduction = """
Welcome to the M&T graphing tool!

Press '`' to see the list of available graphs.
Refresh to read game.log again.

If this is the first run, update the generated config file
in the same folder & restart.
"""

class ChartSelectionDialog(QDialog):
	"""A dialog window to display and select available charts."""
	def __init__(self, graphs_dict, parent=None):
		super().__init__(parent)
		self.setWindowTitle("Select a Chart")
		self.graphs = graphs_dict
		self.selected_chart = None

		self.layout = QVBoxLayout(self)

		self.table = QTableWidget()
		self.table.setColumnCount(2)
		self.table.setHorizontalHeaderLabels(["Chart Name", "Hotkey"])
		self.table.setRowCount(len(self.graphs))
		self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
		self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
		self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
		self.table.verticalHeader().setVisible(False)
		self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

		self.populate_table()

		self.layout.addWidget(self.table)
		self.table.cellDoubleClicked.connect(self.on_double_click)
		self.table.activated.connect(self.on_activated) # Handles Enter key

	def populate_table(self):
		"""Fills the table with chart names and their assigned hotkeys."""
		sorted_charts = sorted(self.graphs.keys())
		for i, chart_name in enumerate(sorted_charts):
			hotkey = str(i + 1)
			self.parent().chart_hotkeys[hotkey] = chart_name # Assign hotkey in main window
			self.table.setItem(i, 0, QTableWidgetItem(chart_name))
			self.table.setItem(i, 1, QTableWidgetItem(hotkey))

	def on_double_click(self, row, column):
		"""Sets the selected chart and closes the dialog on double click."""
		self.accept_selection(row)

	def on_activated(self, index):
		"""Sets the selected chart and closes the dialog on Enter key press."""
		self.accept_selection(index.row())

	def accept_selection(self, row):
		chart_name = self.table.item(row, 0).text()
		self.selected_chart = chart_name
		self.accept()


class MainWindow(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("MEIOU and Taxes Plotter")

		if os.path.exists(icon_path):
			self.setWindowIcon(QIcon(icon_path))
		else:
			print(f"Warning: '{icon_path}' not found. No application icon will be set.")

		self.setGeometry(100, 100, 1800, 800)
		self.setStyleSheet("QPushButton:checked { background-color: #cce8ff; border: 1px solid #99c8ef; }")

		# --- Data and State ---
		self.log_folder = get_log_directory_from_config()
		self.logs = []
		self.data = ""
		self.graphs = {}
		self.chart_hotkeys = {}
		self.chart_shortcuts = []
		self.cursor_hover_handler = None
		self.filter_widgets = []
		self.current_graph_info = None
		self.current_dataset = []
		self.key_configs = {}
		self.filter_widget_map = {}
		self.preset_buttons = []
		self.preset_shortcuts = []
		self.is_log_scale = False
		self.is_moving_average = False
		self.period_value = 5

		# --- Main Layout ---
		self.central_widget = QWidget()
		self.setCentralWidget(self.central_widget)
		self.layout = QVBoxLayout(self.central_widget)

		# --- Matplotlib Canvas ---
		self.fig, self.ax = plt.subplots()
		self.canvas = FigureCanvas(self.fig)
		self.layout.addWidget(self.canvas, 1)

		# --- Matplotlib Toolbar ---
		self.toolbar = NavigationToolbar(self.canvas, self)
		self.layout.addWidget(self.toolbar)

		# --- Top Buttons Layout ---
		self.top_button_layout = QHBoxLayout()
		self.btn_charts = QPushButton("Charts [`]")
		self.btn_export = QPushButton("Export to CSV [Ctrl+E]")
		self.btn_fullscreen = QPushButton("Fullscreen [F]")
		self.btn_refresh = QPushButton("Refresh data [Shift+S]")
		self.btn_backup = QPushButton("Backup logs [Ctrl+S]")
		self.btn_log_scale = QPushButton("Log Scale [L]")
		self.btn_moving_avg = QPushButton("Moving Avg [W]")

		self.btn_fullscreen.setCheckable(True)
		self.btn_log_scale.setCheckable(True)
		self.btn_moving_avg.setCheckable(True)

		self.slider_period = QSlider(Qt.Orientation.Horizontal)
		self.slider_period.setRange(2, 50)
		self.slider_period.setValue(self.period_value)
		self.slider_period.setFixedWidth(100)
		self.lbl_period_value = QLabel(f"Period: {self.period_value}")
		self.slider_period.setVisible(False)
		self.lbl_period_value.setVisible(False)

		self.top_button_layout.addWidget(self.btn_charts)
		self.top_button_layout.addWidget(self.btn_refresh)
		self.top_button_layout.addWidget(self.btn_backup)
		self.top_button_layout.addWidget(self.btn_export)
		self.top_button_layout.addWidget(self.btn_fullscreen)
		self.top_button_layout.addWidget(self.btn_log_scale)
		self.top_button_layout.addWidget(self.btn_moving_avg)
		self.top_button_layout.addWidget(self.slider_period)
		self.top_button_layout.addWidget(self.lbl_period_value)
		self.top_button_layout.addStretch(1)
		self.layout.addLayout(self.top_button_layout)

		self.preset_button_layout = QHBoxLayout()
		self.layout.addLayout(self.preset_button_layout)

		# --- Bottom Filter Widgets Layout ---
		self.filter_layout = QGridLayout()
		self.layout.addLayout(self.filter_layout)

		# --- Connect Signals ---
		self.btn_refresh.clicked.connect(self.reload_log)
		self.btn_backup.clicked.connect(self.backup_log)
		self.btn_charts.clicked.connect(self.show_chart_list)
		self.btn_export.clicked.connect(self.export_to_csv)
		self.btn_fullscreen.toggled.connect(self.set_fullscreen_state)
		self.btn_log_scale.toggled.connect(self.toggle_log_scale)
		self.btn_moving_avg.toggled.connect(self.toggle_moving_average)
		self.slider_period.valueChanged.connect(self.on_period_slider_change)

		# --- Initialize ---
		self.setup_shortcuts()
		self.load_key_configs()
		self.load_graph_definitions()
		self.reload_log()

	def load_key_configs(self):
		try:
			with open("key_configs.json", "r") as f:
				self.key_configs = json.load(f)
				print("Successfully loaded key_configs.json")
		except FileNotFoundError:
			self.key_configs = {}
			print("key_configs.json not found, no function key presets will be available.")
		except json.JSONDecodeError as e:
			self.key_configs = {}
			QMessageBox.critical(self, "Config Error", f"Error parsing key_configs.json:\n{e}")

	def setup_shortcuts(self):
		"""Setup global keyboard shortcuts."""
		QShortcut(QKeySequence("Shift+S"), self, self.reload_log)
		QShortcut(QKeySequence("Ctrl+S"), self, self.backup_log)
		QShortcut(QKeySequence("`"), self, self.show_chart_list)
		QShortcut(QKeySequence("F"), self, self.btn_fullscreen.toggle)
		QShortcut(QKeySequence("Ctrl+E"), self, self.export_to_csv)
		QShortcut(QKeySequence("L"), self, self.btn_log_scale.toggle)
		QShortcut(QKeySequence("W"), self, self.btn_moving_avg.toggle)

	def set_fullscreen_state(self, checked):
		if checked:
			self.showFullScreen()
		else:
			self.showNormal()

	def changeEvent(self, event):
		if event.type() == event.Type.WindowStateChange:
			self.btn_fullscreen.blockSignals(True)
			self.btn_fullscreen.setChecked(self.isFullScreen())
			self.btn_fullscreen.blockSignals(False)
		super().changeEvent(event)

	def load_graph_definitions(self):
		"""Load graph functions from the all_graphs module."""
		all_graphs.get_data = self.get_data
		self.graphs = {
			# Use docstring for title, fallback to formatted name
			(getattr(all_graphs, name).__doc__ or getattr(all_graphs, name).__name__[6:].replace("_", " ").title()):
				getattr(all_graphs, name)
			for name in dir(all_graphs)
			if callable(getattr(all_graphs, name)) and name.lower().startswith("graph")
		}

		configs = {
			'graph_building_types': all_graphs.BT_CONFIG,
			'graph_goods_prices': all_graphs.GP_CONFIG,
			'graph_markets': all_graphs.MK_CONFIG,
			'graph_population': all_graphs.POP_CONFIG,
			'graph_road_types': all_graphs.RT_CONFIG,
		}

		self.graphs = {}
		for name in dir(all_graphs):
			if callable(getattr(all_graphs, name)) and name.lower().startswith("graph"):
				func = getattr(all_graphs, name)
				title = func.__doc__ or name[6:].replace("_", " ").title()

				# Store the function and its associated config together
				if name in configs:
					self.graphs[title] = {
						'func': func,
						'config': configs[name]
					}

		# Setup chart hotkeys (1, 2, 3...)
		sorted_charts = sorted(self.graphs.keys())
		self.chart_shortcuts.clear()
		for i, chart_name in enumerate(sorted_charts):
			hotkey = str(i + 1)
			self.chart_hotkeys[hotkey] = chart_name
			shortcut = QShortcut(QKeySequence(hotkey), self)
			shortcut.activated.connect(partial(self.plot_by_hotkey, hotkey))
			self.chart_shortcuts.append(shortcut)

	def plot_by_hotkey(self, key):
		"""Plots a chart when its numeric hotkey is pressed."""
		chart_name = self.chart_hotkeys.get(key)
		if chart_name:
			graph_info = self.graphs[chart_name]
			self.display_chart(graph_info, chart_name)


	def _reset_filter_layout(self):
		"""
		Removes the old filter layout and replaces it with a new, empty one.
		This is the key to preventing widget misplacement.
		"""

		self.clear_filter_widgets()

		# Remove the old QGridLayout from the main QVBoxLayout
		if self.filter_layout is not None:
			# Delete the layout
			while self.filter_layout.count():
				item = self.filter_layout.takeAt(0)
				widget = item.widget()
				if widget is not None:
					widget.deleteLater()
			self.layout.removeItem(self.filter_layout)
			self.filter_layout.deleteLater()

		# Create and add a fresh, new QGridLayout
		self.filter_layout = QGridLayout()
		self.layout.addLayout(self.filter_layout)

	def display_info_screen(self, msg=None):
		"""Displays the initial welcome message on the plot."""
		self.cursor_hover_handler = None
		self._reset_filter_layout()
		self.clear_preset_buttons()
		self.ax.clear()
		self.ax.set_title("Menu")
		text_to_show = ERROR_FILE_NOT_FOUND if not is_path_found else msg if msg else graph_introduction.strip()
		self.ax.text(0.5, 0.5, text_to_show,
					 horizontalalignment="center", verticalalignment="center")
		self.canvas.draw()
		# Clear current graph state when returning to menu
		self.current_graph_info = None
		self.current_dataset = []

	def get_data(self, _, str_target):
		"""Read data (passed to all_graphs module)."""
		lst = []
		loc = 0
		while True:
			loc = self.data.find(str_target, loc)
			if loc != -1:
				end = self.data.find("\n", loc)
				lst.append(float(self.data[loc:end].strip().split(":")[1].strip().split("£")[-1]))
				loc = end
			else:
				break
		return np.array(lst)

	def clear_filter_widgets(self):
		"""Removes any dynamically added filter widgets from the layout."""
		for widget in self.filter_widgets:
			self.filter_layout.removeWidget(widget)
			widget.deleteLater()
		self.filter_widgets.clear()
		self.filter_widget_map.clear()

	def on_plot_updated(self):
		"""Callback for when the plot is drawn or redrawn."""
		self.setup_tooltip_handler()
		self.apply_plot_settings()

	def setup_tooltip_handler(self):
		"""Creates a new tooltip handler for the current axes."""
		self.cursor_hover_handler = InteractiveLineTooltip(self.ax, on_line_click_callback=self.handle_line_click)
		self.cursor_hover_handler.setup_tooltip_handler()

	def handle_line_click(self, line_label):
		if not self.current_graph_info:
			return

		if self.current_graph_info['title'] == "Market Statistics":
			return

		config = self.current_graph_info['info']['config']
		category_key = config['category_key']

		category_combo = self.filter_widget_map.get(category_key)
		region_combo = self.filter_widget_map.get('region')

		if not category_combo or not region_combo:
			return

		is_category_specific = category_combo.currentIndex() != 0
		is_region_specific = region_combo.currentIndex() != 0

		for combo in [category_combo, region_combo]:
			combo.blockSignals(True)

		try:
			if is_category_specific and not is_region_specific:
				index = region_combo.findText(line_label)
				if index != -1:
					region_combo.setCurrentIndex(index)
					category_combo.setCurrentIndex(0)
			elif is_region_specific and not is_category_specific:
				index = category_combo.findText(line_label)
				if index != -1:
					category_combo.setCurrentIndex(index)
					region_combo.setCurrentIndex(0)
		finally:
			for combo in [category_combo, region_combo]:
				combo.blockSignals(False)

		self.redraw_current_plot()

	def clear_tooltip_handler(self):
		"""Clears any existing tooltip handler."""
		self.cursor_hover_handler = None

	def display_chart(self, graph_info, title):
		"""Clears the axes and plots a new graph."""
		self.current_graph_info = {'info': graph_info, 'title': title}
		self.is_log_scale = False
		self.btn_log_scale.setChecked(False)
		self.is_moving_average = False
		self.btn_moving_avg.setChecked(False)

		# Get the correct parser function from the graph's config.
		parser_func = graph_info['config']['parser']
		# Parse the entire dataset from the raw log data.
		self.current_dataset = parser_func(self.data)
		# Proceed with drawing the chart.
		graph_func = graph_info['func']

		self._reset_filter_layout()
		self.ax.clear()
		self.fig.subplots_adjust(bottom=0.1, left=0.05, right=0.95, top=0.925)

		try:
			graph_func(
				self.data,
				self.ax,
				self.filter_layout,
				self.filter_widgets,
				self.on_plot_updated,
				self.clear_tooltip_handler,
				self.filter_widget_map,
				lambda: self.is_moving_average,
				lambda: self.period_value
			)
			self.ax.set_title(title)
			self.canvas.draw() # Draw the canvas first, to update the graph elements
			self.setup_preset_buttons(title)

		except Exception as e:
			self.ax.text(0.5, 0.5, f"Error:\n{e}", ha='center', va='center')
			traceback.print_exc()

		self.ax.set_title(title)
		self.canvas.draw()

	def clear_preset_buttons(self):
		while self.preset_button_layout.count():
			item = self.preset_button_layout.takeAt(0)
			widget = item.widget()
			if widget is not None:
				widget.deleteLater()

		self.preset_buttons.clear()

		for shortcut in self.preset_shortcuts:
			shortcut.setEnabled(False)
			shortcut.deleteLater()
		self.preset_shortcuts.clear()

	def setup_preset_buttons(self, chart_title):
		self.clear_preset_buttons()
		chart_configs = self.key_configs.get(chart_title, {})

		sorted_keys = sorted(chart_configs.keys(), key=lambda x: int(x[1:]))

		for key in sorted_keys:
			config = chart_configs[key]
			is_valid_preset = True
			for filter_key, filter_value in config.get("filters", {}).items():
				if filter_key not in self.filter_widget_map:
					print(f"Warning for preset {key}: Filter key '{filter_key}' does not exist for this chart.")
					is_valid_preset = False
					break

				combo_box = self.filter_widget_map[filter_key]
				if combo_box.findText(filter_value) == -1:
					print(f"Info for preset {key}: Value '{filter_value}' not found for filter '{filter_key}'. Disabling button.")
					is_valid_preset = False
					break

			description = config.get("description", "No description")
			button_text = f"{description} [{key}]"
			button = QPushButton(button_text)
			button.setToolTip(description)
			button.clicked.connect(partial(self.apply_key_config, config["filters"]))
			button.setEnabled(is_valid_preset)

			self.preset_button_layout.addWidget(button)
			self.preset_buttons.append(button)

			shortcut = QShortcut(QKeySequence(key), self)
			shortcut.activated.connect(partial(self.apply_key_config, config["filters"]))
			shortcut.setEnabled(is_valid_preset)
			self.preset_shortcuts.append(shortcut)

		self.preset_button_layout.addStretch(1)

	def apply_key_config(self, filters):
		print(f"Applying filter preset: {filters}")

		for combo_box in self.filter_widget_map.values():
			combo_box.blockSignals(True)

		try:
			for key, value in filters.items():
				if key in self.filter_widget_map:
					combo_box = self.filter_widget_map[key]
					index = combo_box.findText(value)
					if index != -1:
						combo_box.setCurrentIndex(index)
					else:
						error_message = f"Value '{value}' not found for filter '{key}'.\n\nThe log data may not contain this option."
						QMessageBox.warning(self, "Preset Error", error_message)
						print(f"Warning: {error_message}")
						return
				else:
					error_message = f"Filter key '{key}' not found in widget map."
					QMessageBox.warning(self, "Preset Error", error_message)
					print(f"Warning: {error_message}")
					return
		finally:
			for combo_box in self.filter_widget_map.values():
				combo_box.blockSignals(False)

		self.redraw_current_plot()

	def toggle_log_scale(self, checked):
		if not self.current_graph_info:
			return
		self.is_log_scale = checked
		self.apply_plot_settings()

	def toggle_moving_average(self, checked):
		if not self.current_graph_info:
			return
		self.is_moving_average = checked
		self.slider_period.setVisible(checked)
		self.lbl_period_value.setVisible(checked)
		self.redraw_current_plot()

	def on_period_slider_change(self, value):
		self.period_value = value
		self.lbl_period_value.setText(f"Period: {value}")
		if self.is_moving_average:
			self.redraw_current_plot()

	def redraw_current_plot(self):
		if self.filter_widget_map:
			first_widget = next(iter(self.filter_widget_map.values()))
			if isinstance(first_widget, QComboBox):
				first_widget.currentIndexChanged.emit(first_widget.currentIndex())
			else:
				self.apply_plot_settings()
		else:
			self.apply_plot_settings()

	def apply_plot_settings(self):
		"""Applies current settings (like log scale) to the plot."""
		if not (self.ax.get_lines() or self.ax.patches):
			return

		try:
			if self.is_log_scale:
				self.ax.set_yscale('log')
				bottom, top = self.ax.get_ylim()
				if bottom <= 0:
					self.ax.set_ylim(bottom=0.1)
			else:
				self.ax.set_yscale('linear')
			self.canvas.draw_idle()
		except Exception as e:
			print(f"Could not apply plot settings: {e}")
			self.is_log_scale = False
			self.btn_log_scale.setChecked(False)
			self.ax.set_yscale('linear')
			self.canvas.draw_idle()
			QMessageBox.warning(self, "Scaling Error", "Could not apply logarithmic scale.\nData may contain non-positive values.")

	def export_to_csv(self):
		"""Exports the complete, unfiltered data for the current chart type to a CSV file."""
		if not self.current_dataset:
			QMessageBox.warning(self, "Export Error", "No data available to export. Please select a chart first.")
			return

		default_filename = "export.csv"
		if self.current_graph_info:
			safe_title = self.current_graph_info['title'].lower().replace(" ", "_").replace("/", "")
			default_filename = f"{safe_title}_full_export.csv"

		file_path, _ = QFileDialog.getSaveFileName(
			self, "Save Full Dataset as CSV", default_filename, "CSV Files (*.csv);;All Files (*)"
		)

		if not file_path:
			return

		try:
			headers = self.current_dataset[0].keys()
			with open(file_path, 'w', newline='', encoding='utf-8') as output_file:
				writer = csv.DictWriter(output_file, fieldnames=headers)
				writer.writeheader()
				writer.writerows(self.current_dataset)

			QMessageBox.information(self, "Export Successful", f"Full dataset successfully exported to:\n{file_path}")

		except Exception as e:
			QMessageBox.critical(self, "Export Failed", f"An error occurred while writing the file:\n{e}")
			traceback.print_exc()

	def backup_log(self):
		"""Backs up the current game.log."""
		if not self.logs:
			QMessageBox.critical(self, "Back-up failed", "No log files found to determine the next backup number.")
			return
		number_str = re.findall(r'\d+', self.logs[-1])[0]

		last_log_num = int(number_str) if number_str else 1
		file_to_rename = rf"{self.log_folder}{TARGET_FILE_NAME_ROOT}.log"
		try:
			os.rename(file_to_rename, f"{self.log_folder}{TARGET_FILE_NAME_ROOT}_{last_log_num + 1}.log")
			QMessageBox.information(self, "Back-up complete", f"Backed up {TARGET_FILE_NAME_ROOT}.log to game_{last_log_num + 1}.log")
		except FileNotFoundError:
			QMessageBox.critical(self, "Back-up failed", f"{file_to_rename} not found, nothing to back up.")
		except Exception as e:
			QMessageBox.critical(self, "Back-up failed", f"Error backing up log: {e}")
		self.display_info_screen()

	def reload_log(self):
		"""Reads all log files and refreshes the current view."""
		print("Reloading log data...")
		# Clear the parser caches to force a re-read of the data.

		saved_graph_info = self.current_graph_info
		saved_filters = {}
		saved_is_log_scale = self.is_log_scale
		saved_is_moving_avg = self.is_moving_average
		saved_period_value = self.period_value

		if saved_graph_info:
			for key, widget in self.filter_widget_map.items():
				if isinstance(widget, QComboBox):
					saved_filters[key] = widget.currentText()

		log_parser.clear_all_caches()

		# Read the raw text from the log files.
		self.logs, self.data = self.read_all_logs()

		if saved_graph_info:
			print(f"Refreshing current graph: {saved_graph_info['title']}")
			self.display_chart(saved_graph_info['info'], saved_graph_info['title'])

			self.is_log_scale = saved_is_log_scale
			self.btn_log_scale.setChecked(saved_is_log_scale)
			self.is_moving_average = saved_is_moving_avg
			self.btn_moving_avg.setChecked(saved_is_moving_avg)
			self.period_value = saved_period_value
			self.slider_period.setValue(saved_period_value)

			for widget in self.filter_widget_map.values():
				widget.blockSignals(True)

			for key, value in saved_filters.items():
				if key in self.filter_widget_map:
					widget = self.filter_widget_map[key]
					index = widget.findText(value)
					if index != -1:
						widget.setCurrentIndex(index)
					else:
						print(f"Warning: Saved filter value '{value}' for '{key}' not found after reload. Resetting to default.")
						widget.setCurrentIndex(0)

			for widget in self.filter_widget_map.values():
				widget.blockSignals(False)

			self.redraw_current_plot()
		else:
			# If not (i.e., we are on the main menu), just show the info screen.
			self.display_info_screen()

	def show_chart_list(self):
		"""Opens the chart selection dialog."""
		dialog = ChartSelectionDialog(self.graphs, self)
		self.btn_charts.setDown(True)
		try:
			if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_chart:
				chart_name = dialog.selected_chart
				graph_info = self.graphs[chart_name]
				self.display_chart(graph_info, chart_name)
		finally:
			self.btn_charts.setDown(False)


	def read_all_logs(self):
		"""Read file(s) from a specified directory."""
		content_list = []
		is_path_found = False
		search_pattern = os.path.join(self.log_folder, TARGET_FILE_NAME_ROOT + "_*.log")
		files = glob.glob(search_pattern)
		if files:
			files.sort(key=lambda x: re.findall(r'\d+', x)[0])

		for fn in files:
			with open(fn, "r", encoding="utf-8") as f:
				content_list.append(f.read())
				is_path_found = True

		game_log_path = os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}.log")
		try:
			with open(game_log_path, "r", encoding="utf-8") as f:
				content_list.append(f.read())
				files.append(game_log_path)
				is_path_found = True
		except FileNotFoundError:
			pass

		print(f'Read {len(files) + (1 if os.path.exists(game_log_path) else 0)} log file(s) from "{self.log_folder}"')
		if not is_path_found:
			QMessageBox.critical (self, "No logs found", "Could not find any log files to read.")
		return files, "".join(content_list)



if __name__ == '__main__':
	try:
		# Must change directory to script's location for config/log files
		os.chdir(os.path.dirname(__file__) or '.')

		app = QApplication(sys.argv)
		main_window = MainWindow()
		main_window.show()
		sys.exit(app.exec())

	except Exception as e:
		print(e)
		traceback.print_exc()
		input("\nPress enter to close...")
