# Thanks to the Seelowe/Justice Fighter, the author of the code this is based on
import csv
from datetime import datetime
import glob
import gzip
import json
import os
import pickle
import re
import sys
import traceback
from functools import partial

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence, QIcon, QDesktopServices
from PyQt6.QtWidgets import (QApplication, QDialog, QGridLayout, QHBoxLayout,
							 QHeaderView, QMainWindow, QPushButton,
							 QTableWidget, QTableWidgetItem, QVBoxLayout,
							 QWidget, QFileDialog, QMessageBox, QComboBox, QSlider, QLabel, QProgressDialog,
							 QProgressBar, QTextEdit)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

import chart_library as all_graphs
from interactive_tooltip import InteractiveLineTooltip
from tools.dataset_analysis.analysis_toolkit import AnalysisToolkitDialog
from tools.plot import log_parser
from tools.shared import fetch_logs
from tools.shared.fetch_logs import get_from_config

REFRESH_PERIOD = 5 * 1000
AUTOSAVE_PERIOD = 5 * 60 * 1000
TARGET_FILE_NAME_ROOT = 'error'
columns_not_to_multiply_by_num_of_locations = ['num_locations', 'year', 'age', 'century', 'decade']
ERROR_FILE_NOT_FOUND = f'{TARGET_FILE_NAME_ROOT}.log not found. Please include in the config the correct path to the logs folder'
is_path_found = True
icon_path = 'icon.png'
AUTOSAVE_FILE = "autosave_session.dat"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
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
		self.is_stats_mode = True
		self.current_redraw_fn = None

		if os.path.exists(icon_path):
			self.setWindowIcon(QIcon(icon_path))
		else:
			print(f"Warning: '{icon_path}' not found. No application icon will be set.")

		self.setGeometry(100, 100, 1800, 800)
		self.setStyleSheet("QPushButton:checked { background-color: #cce8ff; border: 1px solid #99c8ef; }")

		# --- Data and State ---
		self.log_folder = get_from_config('Paths', 'log_directory')
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
		self.chart_filter_memory = {}

		# --- Main Layout ---
		self.central_widget = QWidget()
		self.setCentralWidget(self.central_widget)
		self.layout = QVBoxLayout(self.central_widget)

		# --- Canvas and Side Stats Layout ---
		self.fig, self.ax = plt.subplots()
		self.plot_container = QHBoxLayout()
		self.canvas = FigureCanvas(self.fig)
		self.plot_container.addWidget(self.canvas, stretch=4)

		# Side Summary Panel for Statistical Overview
		self.stats_panel = QTextEdit()
		self.stats_panel.setReadOnly(True)
		self.stats_panel.setFixedWidth(320)
		self.stats_panel.setStyleSheet("""
					QTextEdit {
						background-color: #1e1e1e;
						color: #e0e0e0;
						border: 1px solid #3c3c3c;
						border-radius: 4px;
						font-family: Consolas, 'Courier New', monospace;
						font-size: 12px;
						padding: 8px;
						line-height: 1.4;
					}
				""")
		self.stats_panel.setVisible(True)
		self.plot_container.addWidget(self.stats_panel, stretch=1)

		self.layout.addLayout(self.plot_container, 1)

		# Matplotlib Toolbar above canvas
		self.toolbar = NavigationToolbar(self.canvas, self)
		self.layout.addWidget(self.toolbar)

		# --- Top Buttons Layout ---
		self.top_button_layout = QHBoxLayout()
		self.btn_charts = QPushButton("Charts [`]")
		self.btn_change_log_folder = QPushButton("Open log folder [Ctrl+L]")
		self.btn_save_session = QPushButton("Save session [Ctrl+S]")
		self.btn_load_session = QPushButton("Load session [Ctrl+O]")
		self.btn_export_all = QPushButton("Export data [Ctrl+E]")
		self.btn_backup = QPushButton("Backup logs [Shift+S]")
		# self.btn_refresh = QPushButton("Refresh data [Shift+S]")

		# Refresh rate dropdown
		self.combo_refresh = QComboBox()
		self.combo_refresh.addItems(["Refresh: 10s", "Refresh: 30s", "Refresh: 60s", "Refresh: 300s", "Refresh: 600s", "Refresh: Off"])

		# Auto-save dropdown with "No auto-save" option
		self.combo_autosave = QComboBox()
		self.combo_autosave.addItems(["Auto-save: 1m", "Auto-save: 5m", "Auto-save: 10m", "No auto-save"])

		self.btn_fullscreen = QPushButton("Fullscreen [F]")
		self.btn_analysis = QPushButton("Data analysis toolkit [A]")
		self.btn_log_scale = QPushButton("Log scale [L]")
		self.btn_moving_avg = QPushButton("Moving avg [W]")

		self.btn_stats_mode = QPushButton("Stats mode [T]")
		self.btn_stats_mode.setCheckable(True)
		self.btn_stats_mode.setChecked(True)

		self.combo_stats_bands = QComboBox()
		self.combo_stats_bands.addItems(["5 Bands (Quartiles)", "7 Bands (+ 5th/95th)", "9 Bands (+ 1st/99th)"])
		self.combo_stats_bands.setCurrentIndex(2)  # 9 bands by default
		self.combo_stats_bands.setVisible(True)

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

		self.top_button_layout.addWidget(self.btn_change_log_folder)
		self.top_button_layout.addWidget(self.btn_charts)
		# self.top_button_layout.addWidget(self.btn_refresh)
		self.top_button_layout.addWidget(self.combo_refresh)
		self.top_button_layout.addWidget(self.btn_load_session)
		self.top_button_layout.addWidget(self.btn_save_session)
		self.top_button_layout.addWidget(self.combo_autosave)
		self.top_button_layout.addWidget(self.btn_export_all)
		self.top_button_layout.addWidget(self.btn_backup)
		self.top_button_layout.addWidget(self.btn_analysis)
		self.top_button_layout.addWidget(self.btn_fullscreen)
		self.top_button_layout.addWidget(self.btn_log_scale)
		self.top_button_layout.addWidget(self.btn_moving_avg)
		self.top_button_layout.addWidget(self.slider_period)
		self.top_button_layout.addWidget(self.lbl_period_value)
		self.top_button_layout.addWidget(self.combo_stats_bands)
		self.top_button_layout.addWidget(self.btn_stats_mode)
		self.top_button_layout.addStretch(1)
		self.layout.addLayout(self.top_button_layout)

		self.preset_button_layout = QHBoxLayout()
		self.layout.addLayout(self.preset_button_layout)

		# --- Bottom Filter Widgets Layout ---
		self.filter_layout = QGridLayout()
		self.layout.addLayout(self.filter_layout)

		# --- Connect Signals ---
		# self.btn_refresh.clicked.connect(self.reload_log)
		self.combo_refresh.currentIndexChanged.connect(self.on_refresh_rate_changed)
		self.combo_autosave.currentIndexChanged.connect(self.on_autosave_rate_changed)
		self.btn_backup.clicked.connect(self.backup_log)
		self.btn_charts.clicked.connect(self.show_chart_list)
		self.btn_export_all.clicked.connect(self.export_all_data)
		self.btn_fullscreen.toggled.connect(self.set_fullscreen_state)
		self.btn_log_scale.toggled.connect(self.toggle_log_scale)
		self.btn_moving_avg.toggled.connect(self.toggle_moving_average)
		self.slider_period.valueChanged.connect(self.on_period_slider_change)
		self.btn_analysis.clicked.connect(self.open_analysis_toolkit)
		self.btn_change_log_folder.clicked.connect(self.change_log_folder)
		self.btn_stats_mode.toggled.connect(self.toggle_stats_mode)
		self.combo_stats_bands.currentIndexChanged.connect(self.redraw_current_plot)
		self.btn_save_session.clicked.connect(self.manual_save)
		self.btn_load_session.clicked.connect(self.manual_load)

		# --- Initialize ---
		self.setup_shortcuts()
		self.load_key_configs()
		self.load_graph_definitions()
		self.display_info_screen()

		# --- Auto-reload watcher state ---
		self.last_log_state = None

		# --- Auto-reload watcher state ---
		self.timer_auto_reload = QTimer(self)
		self.timer_auto_reload.setInterval(REFRESH_PERIOD)
		self.timer_auto_reload.timeout.connect(self.check_log_updates)
		self.timer_auto_reload.start()

		self.timer_auto_save = QTimer(self)
		self.timer_auto_save.setInterval(AUTOSAVE_PERIOD)
		self.timer_auto_save.timeout.connect(self.auto_save_data)
		self.timer_auto_save.start()

	def on_refresh_rate_changed(self, index):
		intervals = {
			0: 10,
			1: 30,
			2: 60,
			3: 300,
			4: 600,
			5: 0
		}
		ms = 1000 * intervals.get(index, 10)
		if ms == 0:
			self.timer_auto_reload.stop()
		else:
			self.timer_auto_reload.setInterval(ms)
			if not self.timer_auto_reload.isActive():
				self.timer_auto_reload.start()

	def on_autosave_rate_changed(self, index):
		intervals = {
			0: 1 * 60,
			1: 5 * 60,
			2: 10 * 60,
			3: 0
		}
		ms = 1000 * intervals.get(index, 5 * 60)
		if ms == 0:
			self.timer_auto_save.stop()
		else:
			self.timer_auto_save.setInterval(ms)
			if not self.timer_auto_save.isActive():
				self.timer_auto_save.start()

	def load_key_configs(self):
		try:
			with open("key_configs.json", "r") as f:
				self.key_configs = json.load(f)
		except FileNotFoundError:
			self.key_configs = {}
			QMessageBox.warning(self, "No hotkeys", "key_configs.json not found, no function key presets will be available.")
		except json.JSONDecodeError as e:
			self.key_configs = {}
			QMessageBox.critical(self, "Config Error", f"Error parsing key_configs.json:\n{e}")

	def load_initial_data(self):
		"""Checks for a previous session on startup, otherwise loads from logs."""
		if os.path.exists(AUTOSAVE_FILE):
			mod_time = datetime.fromtimestamp(os.path.getmtime(AUTOSAVE_FILE)).strftime("%Y-%m-%d %H:%M")
			msg_box = QMessageBox(self)
			msg_box.setIcon(QMessageBox.Icon.Question)
			msg_box.setWindowTitle("Restore Previous Session?")
			msg_box.setText(f"A saved session from {mod_time} was found.")
			msg_box.setInformativeText("Would you like to continue with the saved data, or read fresh logs from the game directory?")

			btn_restore = msg_box.addButton("Continue with Last Data", QMessageBox.ButtonRole.AcceptRole)
			btn_fresh = msg_box.addButton("Read Fresh Logs", QMessageBox.ButtonRole.RejectRole)
			msg_box.setDefaultButton(btn_restore)

			msg_box.exec()

			if msg_box.clickedButton() == btn_restore:
				if self.load_session_file(AUTOSAVE_FILE):
					return

		# Default: read fresh logs
		self.reload_log(is_interactive=True)

	def setup_shortcuts(self):
		"""Setup global keyboard shortcuts."""
		QShortcut(QKeySequence("Shift+S"), self, self.backup_log)
		QShortcut(QKeySequence("Ctrl+L"), self, self.change_log_folder)
		QShortcut(QKeySequence("A"), self, self.open_analysis_toolkit)
		QShortcut(QKeySequence("`"), self, self.show_chart_list)
		QShortcut(QKeySequence("F"), self, self.btn_fullscreen.toggle)
		QShortcut(QKeySequence("Ctrl+E"), self, self.export_all_data)
		QShortcut(QKeySequence("L"), self, self.btn_log_scale.toggle)
		QShortcut(QKeySequence("W"), self, self.btn_moving_avg.toggle)
		QShortcut(QKeySequence("T"), self, self.btn_stats_mode.toggle)
		QShortcut(QKeySequence("Ctrl+O"), self, self.manual_load)
		QShortcut(QKeySequence("Ctrl+S"), self, self.manual_save)

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

		# In MT_grapher.py, inside the MainWindow class

	def toggle_stats_mode(self, checked):
		self.is_stats_mode = checked
		self.stats_panel.setVisible(checked)
		self.combo_stats_bands.setVisible(checked)
		self.redraw_current_plot()

	def get_stats_bands_count(self):
		idx = self.combo_stats_bands.currentIndex()
		if idx == 0:
			return 5
		elif idx == 1:
			return 7
		return 9

	def load_graph_definitions(self):
		"""Load graph functions from the all_graphs module."""
		all_graphs.get_data = self.get_data
		configs = {
			'graph_building_types': all_graphs.BT_CONFIG,
			'graph_goods_prices': all_graphs.GP_CONFIG,
			'graph_markets': all_graphs.MK_CONFIG,
			'graph_population': all_graphs.POP_CONFIG,
			'graph_road_types': all_graphs.RT_CONFIG,
			'graph_country_metrics': all_graphs.CM_CONFIG,
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
		self.fig.suptitle(None)
		self.ax.set_title("Menu")
		text_to_show = ERROR_FILE_NOT_FOUND if not is_path_found else msg if msg else graph_introduction.strip()
		self.ax.text(0.5, 0.5, text_to_show, horizontalalignment="center", verticalalignment="center")
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
		self.cursor_hover_handler = InteractiveLineTooltip(
			self.ax,
			on_line_click_callback=self.handle_line_click,
			on_stats_hover_callback=self.update_stats_summary_panel # Pass the panel update function
		)
		self.cursor_hover_handler.setup_tooltip_handler()

	def handle_line_click(self, line_label):
		if not self.current_graph_info or self.is_stats_mode:
			return

		if self.current_graph_info['title'] in ("Market Statistics", "Country Metrics"):
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

	def set_redraw_fn(self, fn):
		self.current_redraw_fn = fn

	def redraw_current_plot(self):
		"""Reliably redraws the plot whenever filters or display modes toggle."""
		if callable(self.current_redraw_fn):
			self.current_redraw_fn()
		elif self.filter_widget_map:
			first_widget = next(iter(self.filter_widget_map.values()))
			if isinstance(first_widget, QComboBox):
				first_widget.currentIndexChanged.emit(first_widget.currentIndex())
			else:
				self.apply_plot_settings()
		else:
			self.apply_plot_settings()

	def display_chart(self, graph_info, title):
		"""Clears the axes and plots a new graph."""
		if self.current_graph_info:
			prev_title = self.current_graph_info['title']
			current_filters = {key: widget.currentText() for key, widget in self.filter_widget_map.items() if isinstance(widget, QComboBox)}
			self.chart_filter_memory[prev_title] = current_filters

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
		self.fig.suptitle(title)
		self.fig.subplots_adjust(bottom=0.1, left=0.05, right=0.95, top=0.90)

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
				lambda: self.period_value,
				lambda: self.is_stats_mode,
				self.update_stats_summary_panel,
				self.get_stats_bands_count,
				set_redraw_fn=self.set_redraw_fn
			)
			self.canvas.draw() # Draw the canvas first, to update the graph elements
			self.setup_preset_buttons(title)

			for widget in self.filter_widget_map.values():
				widget.blockSignals(True)

			try:
				if title in self.chart_filter_memory:
					saved_filters = self.chart_filter_memory[title]
					for key, value in saved_filters.items():
						if key in self.filter_widget_map:
							widget = self.filter_widget_map[key]
							index = widget.findText(value)
							if index != -1:
								widget.setCurrentIndex(index)
				elif title in self.key_configs and "F1" in self.key_configs[title]:
					f1_config = self.key_configs[title]["F1"]
					is_valid = all(
						key in self.filter_widget_map and self.filter_widget_map[key].findText(value) != -1
						for key, value in f1_config['filters'].items()
					)
					if is_valid:
						for key, value in f1_config['filters'].items():
							widget = self.filter_widget_map[key]
							index = widget.findText(value)
							widget.setCurrentIndex(index)
			finally:
				for widget in self.filter_widget_map.values():
					widget.blockSignals(False)

			self.redraw_current_plot()

		except Exception as e:
			self.ax.text(0.5, 0.5, f"Error:\n{e}", ha='center', va='center')
			traceback.print_exc()

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
					is_valid_preset = False
					break

				combo_box = self.filter_widget_map[filter_key]
				if combo_box.findText(filter_value) == -1:
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
						QMessageBox.warning(self, "Preset Error", f"Value '{value}' not found for filter '{key}'.")
						return
				else:
					QMessageBox.warning(self, "Preset Error", f"Filter key '{key}' not found in widget map.")
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

	def _check_file_locks(self, export_folder_path, filenames):
		"""
		Checks if any of the target CSV files in the export directory are locked.
		Returns the full path of the first locked file found, or None if all are writable.
		"""
		# Also check for the derived 'normalized' file
		filenames_to_check = list(filenames)
		if "country_stats" in filenames_to_check:
			filenames_to_check.append("country_stats_normalized")

		for name in filenames_to_check:
			full_path = os.path.join(export_folder_path, f"{name}.csv")

			if os.path.exists(full_path):
				try:
					# The most reliable way to check for a lock is to try to open it.
					# We use append mode ('a') as it's a non-destructive write test.
					file = open(full_path, 'a')
					file.close()
				except (IOError, PermissionError):
					return full_path
		return None

	def export_all_data(self):
		"""
		Exports all parsable data. For country_stats, it also generates a second CSV
		where numeric values are multiplied by the number of locations.
		Returns True on success, False on failure or cancellation."""

		if not self.data:
			QMessageBox.warning(self, "Export Error", "No log data loaded. Please refresh data first.")
			return False

		# Define all available parsers and their desired filenames
		all_parsers = {
			"building_types": log_parser.parse_data_building_types,
			"goods_prices": log_parser.parse_data_goods_prices,
			"markets": log_parser.parse_data_markets,
			"population": log_parser.parse_data_population,
			"road_types": log_parser.parse_data_road_types,
			"country_stats": log_parser.parse_data_countries,
		}

		# Define a fixed export path inside the log folder
		export_folder_path = os.path.join(self.log_folder, "csv_export")

		# Pre-check for locked files
		locked_file = self._check_file_locks(export_folder_path, list(all_parsers.keys()))
		if locked_file:
			QMessageBox.critical(self, "File In Use", f"Please close the file and try again:\n\n{locked_file}")
			return False

		location_lookup = self._load_location_data()

		# --- Setup Progress Dialog ---
		progress_dialog = QProgressDialog("Preparing to export...", "Cancel", 0, len(all_parsers), self)
		progress_dialog.setWindowTitle("Export Progress")
		progress_dialog.setModal(True)

		# Style
		progress_dialog.resize(650, 150)
		progress_dialog.show()
		QApplication.processEvents() # Ensure the dialog is shown immediately

		try:
			os.makedirs(export_folder_path, exist_ok=True)
			exported_files = []
			was_cancelled = False

			for i, (filename_root, parser_func) in enumerate(all_parsers.items()):
				# Update progress and check for cancellation
				progress_dialog.setValue(i)
				progress_dialog.setLabelText(f"Parsing and writing {filename_root}...")
				QApplication.processEvents()

				if progress_dialog.wasCanceled():
					was_cancelled = True
					break

				dataset = parser_func(self.data)
				if not dataset:
					continue

				# Add region, subcontinent & continent based on the location.csv file
				if filename_root == "country_stats" and location_lookup:
					enhanced_dataset = []
					for record in dataset:
						capital_area = record.get('capital_area')
						geo_data = location_lookup.get(capital_area, {})
						enhanced_record = {
							'continent': geo_data.get('continent', 'N/A'),
							'subcontinent': geo_data.get('subcontinent', 'N/A'),
							'region': geo_data.get('region', 'N/A'),
						}
						enhanced_record.update(record)
						enhanced_dataset.append(enhanced_record)
					dataset_to_write = enhanced_dataset
				else:
					dataset_to_write = dataset

				file_path = os.path.join(export_folder_path, f"{filename_root}.csv")
				try:
					headers = dataset_to_write[0].keys()
					with open(file_path, 'w', newline='', encoding='utf-8') as output_file:
						writer = csv.DictWriter(output_file, fieldnames=headers)
						writer.writeheader()
						writer.writerows(dataset_to_write)
					exported_files.append(file_path)

					# Generate the location-multiplied CSV
					if filename_root == "country_stats" and dataset_to_write:
						df = pd.DataFrame(dataset_to_write)
						if 'num_locations' in df.columns:
							df_cleaned = df[df['num_locations'] > 0].copy()
							estate_types = ['nobles', 'clergy', 'burghers', 'peasants', 'dhimmi', 'tribes', 'cossacks']
							for estate in estate_types:
								power_col = f'{estate}_relative_power'
								if power_col in df_cleaned.columns:
									no_power_mask = df_cleaned[power_col] == 0
									stats_cols = [col for col in df_cleaned.columns if col.startswith(f'{estate}_')]
									df_cleaned.loc[no_power_mask, stats_cols] = np.nan

							new_filepath = os.path.join(export_folder_path, "country_stats_cleaned.csv")
							df_cleaned.to_csv(new_filepath, index=False)
							exported_files.append(new_filepath)

				except Exception as e:
					QMessageBox.critical(self, "File Write Error", f"Failed to write {filename_root}.csv: {e}")
					# Continue to the next file even if one fails

			# Finalize the progress bar
			progress_dialog.setValue(len(all_parsers))

			# --- Show Final Status Message ---
			if was_cancelled:
				QMessageBox.information(self, "Export Cancelled", f"Export process was cancelled.\nPartial files may exist in:\n{export_folder_path}")
				return False # Return failure status
			elif exported_files:
				# --- Create a custom message box with an "Open Directory" button ---
				msg_box = QMessageBox(self)
				msg_box.setIcon(QMessageBox.Icon.Information)
				msg_box.setWindowTitle("Export Successful")
				msg_box.setText(f"All data successfully exported to the 'csv_export' subfolder:\n{export_folder_path}")
				open_button = msg_box.addButton("Open Directory", QMessageBox.ButtonRole.ActionRole)
				msg_box.addButton(QMessageBox.StandardButton.Ok)
				msg_box.exec()

				if msg_box.clickedButton() == open_button:
					# Use QDesktopServices for cross-platform compatibility to open the folder
					QDesktopServices.openUrl(QUrl.fromLocalFile(export_folder_path))
				return True
			else:
				QMessageBox.warning(self, "Export Warning", "No data was available to export.")
				return False

		except Exception as e:
			progress_dialog.close() # Ensure dialog is closed on error
			QMessageBox.critical(self, "Export Failed", f"A critical error occurred:\n{e}")
			traceback.print_exc()
			return False

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
		except Exception as e:
			QMessageBox.critical(self, "Back-up failed", f"Error backing up log: {e}")
		self.display_info_screen()

	def reload_log(self, is_interactive=True):
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

		# Prompt user if no logs are found during an interactive load
		if is_interactive and not self.logs:
			msg_box = QMessageBox(self)
			msg_box.setIcon(QMessageBox.Icon.Warning)
			msg_box.setWindowTitle("No Log Files Found")
			msg_box.setText(f"No log files were found in the configured directory:\n\n{self.log_folder}")
			msg_box.setInformativeText("Would you like to select the correct log folder now?")
			msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
			msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

			if msg_box.exec() == QMessageBox.StandardButton.Yes:
				self.change_log_folder()
				return # Stop the current reload process, as a new one will be started.

		if saved_graph_info:
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

	def get_all_log_files(self):
		"""
		Finds active and rotated log files in chronological order:
		error.5.log -> error.4.log -> ... -> error.1.log -> error.log
		"""
		file_list = []

		# Rotated game logs: error.<number>.log (e.g. error.5.log down to error.1.log)
		rotated_pattern = os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}.*.log")
		rotated_files = glob.glob(rotated_pattern)
		if rotated_files:
			# Sort by the number in descending order (highest number is oldest)
			def get_log_num(path):
				nums = re.findall(r'\.(\d+)\.log$', os.path.basename(path))
				return int(nums[0]) if nums else -1

			rotated_files.sort(key=get_log_num, reverse=True)
			file_list.extend(rotated_files)

		# Manual backups if any exist: error_<number>.log
		manual_pattern = os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}_*.log")
		manual_files = glob.glob(manual_pattern)
		if manual_files:
			manual_files.sort(key=lambda x: int(re.findall(r'\d+', os.path.basename(x))[-1]))
			file_list.extend(manual_files)

		# Active log: error.log (newest lines)
		active_log_path = os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}.log")
		if os.path.exists(active_log_path):
			file_list.append(active_log_path)

		return file_list

	def read_all_logs(self):
		"""Reads all files in chronological order."""
		content_list = []
		files = self.get_all_log_files()

		for fn in files:
			try:
				# Use errors='replace' to safely handle partial writes at EOF
				with open(fn, "r", encoding="utf-8", errors="replace") as f:
					content_list.append(f.read())
			except (IOError, PermissionError) as e:
				print(f"Warning: Could not read {fn}: {e}")

		return files, "".join(content_list)

	def _load_location_data(self, filepath="locations.csv"):
		"""
		Loads the locations.csv file and returns a dictionary for quick lookups.
		The dictionary maps an area name to its continent, subcontinent, and region.
		"""
		location_map = {}
		try:
			with open(filepath, mode='r', encoding='utf-8') as infile:
				reader = csv.DictReader(infile)
				for row in reader:
					area = row.get('area')
					if area:
						location_map[area] = {
							'continent': row.get('continent', 'N/A'),
							'subcontinent': row.get('subcontinent', 'N/A'),
							'region': row.get('region', 'N/A')
						}
		except Exception:
			pass
		return location_map

	def open_analysis_toolkit(self):
		"""
		Opens the analysis toolkit by reading the pre-generated country_stats.csv file
		from the 'csv_export' subfolder in the log directory.
		"""
		csv_path = os.path.join(self.log_folder, "csv_export", "country_stats.csv")

		if not os.path.exists(csv_path):
			# File is missing, so we ask the user if they want to create it.
			msg_box = QMessageBox(self)
			msg_box.setIcon(QMessageBox.Icon.Question)
			msg_box.setWindowTitle("CSV File Not Found")
			msg_box.setText("The required 'country_stats.csv' file was not found.")
			msg_box.setInformativeText("Would you like to generate it now? This may take a moment.")
			msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
			msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

			if msg_box.exec() == QMessageBox.StandardButton.Yes:
				if self.export_all_data():
					self.open_analysis_toolkit()
			return # Exit the function here, as the flow is handled by the user's choice.

		# If we get here, the file exists (either from the start or after generation).
		try:
			# Get total number of rows for the progress bar maximum1
			print("Counting rows for progress bar...")
			with open(csv_path, 'r', encoding='utf-8') as f:
				total_rows = sum(1 for _ in f) - 1

			# Setup and show the progress dialog
			progress_dialog = QProgressDialog("Loading data...", "Cancel", 0, total_rows, self)
			progress_dialog.setWindowTitle("Loading Analysis Data")
			progress_dialog.setModal(True)
			progress_dialog.show()
			QApplication.processEvents()

			# Read the CSV in chunks and update the progress
			chunk_size = 50000  # Rows to process at a time
			chunks = []
			rows_processed = 0

			user_cancelled = False

			reader = pd.read_csv(csv_path, chunksize=chunk_size, low_memory=False)
			for chunk in reader:
				if progress_dialog.wasCanceled():
					user_cancelled = True
					break

				chunks.append(chunk)
				rows_processed += len(chunk)
				progress_dialog.setValue(rows_processed)
				QApplication.processEvents() # Keep the UI responsive

			progress_dialog.close()

			# If not cancelled, combine chunks into the final DataFrame
			if not user_cancelled:
				country_df = pd.concat(chunks, ignore_index=True)
				if country_df.empty:
					QMessageBox.warning(self, "No Data", "The 'country_stats.csv' file is empty.")
					return

				# Launch the toolkit with the loaded data
				dialog = AnalysisToolkitDialog(country_df, self)
				dialog.exec()
			else:
				print("Data loading was cancelled by the user.")

		except FileNotFoundError:
			# This case is now handled by the initial check, but kept as a fallback.
			QMessageBox.warning(self, "File Not Found", "The 'country_stats.csv' file was not found.")
		except Exception as e:
			QMessageBox.critical(self, "Error Loading Data", f"An error occurred while reading the CSV file:\n{e}")

	def change_log_folder(self):
		"""Opens a dialog to select a new log folder and updates the config."""
		path_new_folder = QFileDialog.getExistingDirectory(self, "Select Log Folder", self.log_folder)
		if path_new_folder and path_new_folder != self.log_folder:
			self.log_folder = path_new_folder

			# --- Use the centralized function to update the config file ---
			fetch_logs.update_config_file('Paths', 'log_directory', path_new_folder)
			QMessageBox.information(self, "Log Folder Changed", f"The application will now refresh data from:\n{path_new_folder}")
			self.reload_log()

	def check_log_updates(self):
		"""Checks if any log file was modified or changed size. If so, reloads."""
		files = self.get_all_log_files()
		if not files:
			return

		# Create a fingerprint of file sizes and modification times
		current_state = []
		for f in files:
			try:
				stat = os.stat(f)
				current_state.append((f, stat.st_size, stat.st_mtime))
			except OSError:
				return  # File being rotated or locked by the game, retry next second

		if self.last_log_state is None:
			self.last_log_state = current_state
			return

		# If file size or timestamp changed, refresh data
		if current_state != self.last_log_state:
			self.last_log_state = current_state
			self.reload_log(is_interactive=False)

	def update_stats_summary_panel(self, global_stats, year_stats=None):
		if not global_stats or not self.is_stats_mode:
			self.stats_panel.clear()
			return

		y_label = global_stats.get('value_label', '')
		is_integer = y_label in ("Population", "Count")
		fmt = ",.0f" if is_integer else ",.2f"

		text = []
		if year_stats:
			text.append(f"=== STATS FOR {year_stats['year']} ===")
			text.append(f"Count:      {year_stats['count']}")
			text.append(f"Mean:       {year_stats['mean']:{fmt}}")
			text.append(f"Median:     {year_stats['median']:{fmt}}")
			text.append(f"Std Dev:    {year_stats['std']:{fmt}}")
		else:
			text.append("Hover plot to see yearly stats")

		text.append("\n" + "="*30 + "\n")
		text.append("=== GLOBAL OVERVIEW ===")
		text.append(f"Avg Mean:   {global_stats['overall_mean']:{fmt}}")
		text.append(f"Avg StdDev: {global_stats['overall_std']:{fmt}}")

		text.append("\n--- BIGGEST GAINERS (Full Game) ---")
		for reg, delta, start, end, _ in global_stats['biggest_increase']:
			text.append(f"{reg[:12]:<12}: +{delta:{fmt}} ({start:{fmt}} → {end:{fmt}})")

		text.append("\n--- BIGGEST DECLINES (Full Game) ---")
		for reg, delta, start, end, _ in global_stats['biggest_decrease']:
			text.append(f"{reg[:12]:<12}: {delta:{fmt}} ({start:{fmt}} → {end:{fmt}})")

		text.append("\n--- HIGHEST VOLATILITY (σ) ---")
		for reg, _, _, _, std in global_stats['most_volatile']:
			text.append(f"{reg[:12]:<12}: σ = {std:{fmt}}")

		self.stats_panel.setPlainText("\n".join(text))

	# SESSION SAVE & LOAD SYSTEM ---------------------------------------------------------------------
	def save_session_file(self, filepath=AUTOSAVE_FILE, show_popup=False):
		"""Serializes logs, cumulative country records, and filter states into a compressed file."""
		if not self.data:
			if show_popup:
				QMessageBox.warning(self, "Save Warning", "No data loaded to save.")
			return False

		try:
			session = {
				"version": 1,
				"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
				"data": self.data,
				"logs": self.logs,
				"cumulative_store": {f"{int(k[0])}:{k[1]}": v for k, v in log_parser.tg_cumulative_store.items()},
				"chart_filter_memory": self.chart_filter_memory,
				"current_chart": self.current_graph_info['title'] if self.current_graph_info else None
			}

			with gzip.open(filepath, "wb") as f:
				pickle.dump(session, f)

			if show_popup:
				QMessageBox.information(self, "Session Saved", f"Session saved successfully to:\n{filepath}")
			return True
		except Exception as e:
			if show_popup:
				QMessageBox.critical(self, "Save Error", f"Failed to save session:\n{e}")
			return False

	def load_session_file(self, filepath=AUTOSAVE_FILE):
		"""Loads a saved session file and restores the graph view."""
		if not os.path.exists(filepath):
			QMessageBox.warning(self, "File Not Found", f"No session file found at:\n{filepath}")
			return False

		try:
			with gzip.open(filepath, "rb") as f:
				session = pickle.load(f)

			self.data = session.get("data", "")
			self.logs = session.get("logs", [])

			# Restore cumulative country store
			log_parser.tg_cumulative_store.clear()
			for k_str, v in session.get("cumulative_store", {}).items():
				parts = k_str.split(":", 1)
				if len(parts) == 2:
					log_parser.tg_cumulative_store[(int(parts[0]), parts[1])] = v

			log_parser.clear_all_caches()
			self.chart_filter_memory = session.get("chart_filter_memory", {})

			# Display chart or menu
			chart_name = session.get("current_chart")
			if chart_name and chart_name in self.graphs:
				self.display_chart(self.graphs[chart_name], chart_name)
			else:
				self.display_info_screen("Session loaded successfully.")
			return True

		except Exception as e:
			QMessageBox.critical(self, "Load Error", f"Could not load session:\n{e}")
			traceback.print_exc()
			return False

	def manual_save(self):
		"""Opens a dialog to save data to a chosen file."""
		path, _ = QFileDialog.getSaveFileName(self, "Save Session", "session_backup.dat", "Session Data (*.dat)")
		if path:
			self.save_session_file(path, show_popup=True)

	def manual_load(self):
		"""Opens a dialog to pick and load any saved session."""
		path, _ = QFileDialog.getOpenFileName(self, "Load Session", "", "Session Data (*.dat);;All Files (*.*)")
		if path:
			self.load_session_file(path)

	def auto_save_data(self):
		if self.combo_autosave.currentIndex() == 3:  # No auto-save
			return
		if self.data:
			self.save_session_file(AUTOSAVE_FILE, show_popup=False)

	def closeEvent(self, event):
		if not self.data or self.combo_autosave.currentIndex() == len(self.combo_autosave) - 1:
			event.accept()
			return

		reply = QMessageBox.question(
			self,
			"Save on Exit",
			"Do you want to save your current session data before exiting?",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
			QMessageBox.StandardButton.Yes
		)

		if reply == QMessageBox.StandardButton.Yes:
			self.save_session_file(AUTOSAVE_FILE, show_popup=False)
			event.accept()
		elif reply == QMessageBox.StandardButton.No:
			event.accept()
		else:
			event.ignore()  # Abort exiting


class LoadingDialog(QDialog):
	"""A simple, frameless dialog to show while the main application is loading."""

	def __init__(self):
		super().__init__()
		self.setWindowTitle("Loading Application")
		self.setFixedSize(350, 120)
		# Make it a frameless dialog that stays on top
		self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
		self.setModal(True)

		layout = QVBoxLayout(self)

		self.label = QLabel("Loading log files, please wait...")
		self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
		font = self.label.font()
		font.setPointSize(10)
		self.label.setFont(font)
		layout.addWidget(self.label)

		# An "indeterminate" progress bar shows a busy animation without needing a specific value.
		self.progress = QProgressBar()
		self.progress.setRange(0, 0)  # Setting min and max to 0 enables indeterminate mode
		layout.addWidget(self.progress)


if __name__ == '__main__':
	try:
		app = QApplication(sys.argv)

		main_window = MainWindow()
		main_window.show()

		# Show the loading screen on top of the main window.
		loading_dialog = LoadingDialog()
		loading_dialog.show()
		app.processEvents() # Ensure the loading dialog appears immediately.

		# Run the slow data loading process.
		main_window.load_initial_data()
		# Once loading is complete, close the loading screen.
		loading_dialog.close()
		# Start the main application event loop.
		sys.exit(app.exec())

	except Exception as e:
		print(e)
		traceback.print_exc()
		input("\nPress enter to close...")

