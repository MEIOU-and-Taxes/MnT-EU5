import glob
import json
import os
import re
import shutil
from datetime import datetime
from functools import partial

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QShortcut, QKeySequence, QIcon, QAction, QDesktopServices
from PyQt6.QtWidgets import (
	QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
	QPushButton, QComboBox, QTextEdit, QMessageBox,
	QFileDialog, QLabel
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

from src.analysis_toolkit import AnalysisToolkitDialog
from src.constants import (
	REFRESH_PERIOD_MS, AUTOSAVE_PERIOD_MS, TARGET_FILE_NAME_ROOT,
	AUTOSAVE_FILE, AUTOSAVE_DIR, APPDATA_DIR, KEY_CONFIGS_PATH,
	SETTINGS_PATH, ICON_PATH, GRAPH_INTRODUCTION, AUTOSAVES_KEPT,
	POS_SUBPLOT_TOP_EDGE, POS_SUBPLOT_BOTTOM_EDGE,
	POS_SUBPLOT_LEFT_EDGE, POS_SUBPLOT_RIGHT_EDGE,
	POS_SUBPLOT_HSPACE, POS_SUBPLOT_WSPACE, PRESETS_PER_PAGE
)
from src.parsing import log_parser
from src.plotting import chart_library, configs
from src.plotting.tooltip import InteractiveLineTooltip
from src.services.exporter import run_export_pipeline
from src.services.session_manager import save_session, load_session
from src.ui.stats_panel import format_stats_panel_text
from src.widgets.dialogs import ChartSelectionDialog, PresetConfigDialog, SettingsDialog, sort_hotkeys, \
	FilterSearchDialog
from tools.shared import fetch_logs
from tools.shared.fetch_logs import get_from_config

STATS_PANEL_WIDTH = 420

class MainWindow(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("MEIOU and Taxes Plotter")
		self.is_stats_mode = True
		self.current_redraw_fn = None
		self._handling_mismatch = False

		# Register callback for column count mismatch in country logs
		log_parser.set_column_mismatch_callback(self.handle_column_mismatch)

		if os.path.exists(ICON_PATH):
			self.setWindowIcon(QIcon(ICON_PATH))

		self.setGeometry(100, 100, 1800, 800)
		self.setStyleSheet("QPushButton:checked { background-color: #cce8ff; border: 1px solid #99c8ef; }")

		# State
		self.log_folder = get_from_config('Paths', 'log_directory')
		self.logs = []
		self.data = ""
		self.graphs = {}
		self.chart_hotkeys = {}
		self.chart_shortcuts = []
		self.cursor_hover_handler = None
		self.filter_widgets = []
		self.current_graph_info = None
		self.key_configs = {}
		self.filter_widget_map = {}
		self.preset_buttons = []
		self.preset_shortcuts = []
		self.preset_page = 0
		self.current_preset_chart = None
		self.is_log_scale = False
		self.is_moving_average = False
		self.is_density = False
		self.is_year_offset = False
		self.stats_hide_idx = 0
		self.period_value = 5
		self.refresh_interval_idx = 0
		self.autosave_interval_idx = 1
		self.chart_filter_memory = {}
		self.last_log_state = None
		self.has_new_data = False
		self.stats_shading_all = True

		self.load_app_settings()

		self._build_menu()
		self._build_ui()
		self.setup_shortcuts()
		self.load_key_configs()
		self.load_graph_definitions()
		self.display_info_screen()

		# Constant 5-second watcher: checks and reads log files from disk
		self.timer_file_watcher = QTimer(self)
		self.timer_file_watcher.setInterval(REFRESH_PERIOD_MS)
		self.timer_file_watcher.timeout.connect(self.check_log_updates)
		self.timer_file_watcher.start()

		# Graph re-render timer: controlled by combo_refresh
		self.timer_graph_refresh = QTimer(self)
		self.timer_graph_refresh.setInterval(10 * 1000)
		self.timer_graph_refresh.timeout.connect(self.auto_refresh_graph)
		self.timer_graph_refresh.start()
		self._apply_refresh_interval()

		# Auto-save timer
		self.timer_auto_save = QTimer(self)
		self.timer_auto_save.setInterval(AUTOSAVE_PERIOD_MS)
		self.timer_auto_save.timeout.connect(self.auto_save_data)
		self.timer_auto_save.start()
		self._apply_autosave_interval()

	def load_app_settings(self):
		if not os.path.exists(SETTINGS_PATH):
			return
		try:
			with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
				data = json.load(f)
			self.refresh_interval_idx = data.get("refresh_interval_idx", 0)
			self.autosave_interval_idx = data.get("autosave_interval_idx", 1)
			self.period_value = data.get("period_value", 5)
			self.is_stats_mode = data.get("is_stats_mode", True)
			self.stats_hide_idx = data.get("stats_hide_idx", 0)
			self.is_density = data.get("is_density", False)
			self.is_year_offset = data.get("is_year_offset", False)
			self.is_log_scale = data.get("is_log_scale", False)
			self.is_moving_average = data.get("is_moving_average", False)
			self.stats_shading_all = data.get("stats_shading_all", True)
		except Exception as e:
			print(f"Failed to load settings from {SETTINGS_PATH}: {e}")

	def save_app_settings(self):
		try:
			data = {
				"refresh_interval_idx": self.refresh_interval_idx,
				"autosave_interval_idx": self.autosave_interval_idx,
				"period_value": self.period_value,
				"is_stats_mode": self.is_stats_mode,
				"stats_hide_idx": self.combo_stats_hide.currentIndex() if hasattr(self, 'combo_stats_hide') else self.stats_hide_idx,
				"is_density": self.is_density,
				"is_year_offset": self.is_year_offset,
				"is_log_scale": self.is_log_scale,
				"is_moving_average": self.is_moving_average,
				"stats_shading_all": self.stats_shading_all,
			}
			with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
				json.dump(data, f, indent=2)
		except Exception as e:
			print(f"Failed to save settings to {SETTINGS_PATH}: {e}")

	def _build_menu(self):
		menubar = self.menuBar()

		# File Menu
		menu_file = menubar.addMenu("&File")

		act_open_folder = QAction("Open Log Folder", self)
		act_open_folder.setShortcut(QKeySequence("Ctrl+L"))
		act_open_folder.triggered.connect(self.change_log_folder)
		menu_file.addAction(act_open_folder)

		act_backup = QAction("Backup Logs", self)
		act_backup.setShortcut(QKeySequence("Shift+S"))
		act_backup.triggered.connect(self.backup_log)
		menu_file.addAction(act_backup)

		menu_file.addSeparator()

		act_load_sess = QAction("Load Session...", self)
		act_load_sess.setShortcut(QKeySequence("Ctrl+O"))
		act_load_sess.triggered.connect(self.manual_load)
		menu_file.addAction(act_load_sess)

		act_save_sess = QAction("Save Session...", self)
		act_save_sess.setShortcut(QKeySequence("Ctrl+S"))
		act_save_sess.triggered.connect(self.manual_save)
		menu_file.addAction(act_save_sess)

		act_clear_data = QAction("Clear Data...", self)
		act_clear_data.triggered.connect(self.clear_data)
		menu_file.addAction(act_clear_data)

		menu_file.addSeparator()

		act_export = QAction("Export Data to CSV", self)
		act_export.setShortcut(QKeySequence("Ctrl+E"))
		act_export.triggered.connect(lambda: run_export_pipeline(self.data, self.log_folder, self))
		menu_file.addAction(act_export)

		act_appdata = QAction("Open AppData Folder", self)
		act_appdata.triggered.connect(self.open_appdata_folder)
		menu_file.addAction(act_appdata)

		menu_file.addSeparator()

		act_exit = QAction("Exit", self)
		act_exit.triggered.connect(self.close)
		menu_file.addAction(act_exit)

		# Charts Menu
		menu_charts = menubar.addMenu("&Charts")

		act_charts = QAction("Select Chart...", self)
		act_charts.setShortcut(QKeySequence("`"))
		act_charts.triggered.connect(self.show_chart_list)
		menu_charts.addAction(act_charts)

		act_presets = QAction("Configure Presets...", self)
		act_presets.setShortcut(QKeySequence("P"))
		act_presets.triggered.connect(self.open_preset_config)
		menu_charts.addAction(act_presets)

		# View Menu
		menu_view = menubar.addMenu("&View")

		act_find = QAction("Find Filter / Metric...", self)
		act_find.setShortcut(QKeySequence("Ctrl+F"))
		act_find.triggered.connect(self.open_filter_search)
		menu_view.addAction(act_find)
		self.addAction(act_find)

		self.act_fullscreen = QAction("Fullscreen", self, checkable=True)
		self.act_fullscreen.setShortcut(QKeySequence("F"))
		self.act_fullscreen.toggled.connect(self.toggle_fullscreen)
		menu_view.addAction(self.act_fullscreen)

		self.act_stats_mode = QAction("Stats mode", self, checkable=True)
		self.act_stats_mode.setChecked(self.is_stats_mode)
		self.act_stats_mode.setShortcut(QKeySequence("T"))
		self.act_stats_mode.toggled.connect(self.toggle_stats_mode)
		menu_view.addAction(self.act_stats_mode)

		self.act_year_offset = QAction("Relative year", self, checkable=True)
		self.act_year_offset.setChecked(self.is_year_offset)
		self.act_year_offset.setShortcut(QKeySequence("Y"))
		self.act_year_offset.toggled.connect(self.toggle_year_offset)
		menu_view.addAction(self.act_year_offset)

		self.act_density = QAction("Density mode", self, checkable=True)
		self.act_density.setChecked(self.is_density)
		self.act_density.setShortcut(QKeySequence("D"))
		self.act_density.toggled.connect(self.toggle_density)
		menu_view.addAction(self.act_density)

		self.act_log_scale = QAction("Symlog scale", self, checkable=True)
		self.act_log_scale.setChecked(self.is_log_scale)
		self.act_log_scale.setShortcut(QKeySequence("L"))
		self.act_log_scale.toggled.connect(self.toggle_log_scale)
		menu_view.addAction(self.act_log_scale)

		self.act_moving_avg = QAction("Moving average", self, checkable=True)
		self.act_moving_avg.setChecked(self.is_moving_average)
		self.act_moving_avg.setShortcut(QKeySequence("W"))
		self.act_moving_avg.toggled.connect(self.toggle_moving_average)
		self.act_moving_avg.setVisible(self.is_stats_mode)
		menu_view.addAction(self.act_moving_avg)

		act_hide_inc = QAction("Hide more percentiles", self)
		act_hide_inc.setShortcut(QKeySequence("["))
		act_hide_inc.triggered.connect(self.increase_stats_hide)
		menu_view.addAction(act_hide_inc)
		self.addAction(act_hide_inc)

		act_hide_dec = QAction("Show more percentiles", self)
		act_hide_dec.setShortcut(QKeySequence("]"))
		act_hide_dec.triggered.connect(self.decrease_stats_hide)
		menu_view.addAction(act_hide_dec)
		self.addAction(act_hide_dec)

		self.act_stats_shading_all = QAction("Shade all percentile bands", self, checkable=True)
		self.act_stats_shading_all.setChecked(self.stats_shading_all)
		self.act_stats_shading_all.toggled.connect(self.toggle_stats_shading_all)
		menu_view.addAction(self.act_stats_shading_all)
		self.addAction(self.act_stats_shading_all)

		# Tools Menu
		menu_tools = menubar.addMenu("&Tools")

		act_refresh = QAction("Refresh Logs", self)
		act_refresh.setShortcut(QKeySequence("Ctrl+R"))
		act_refresh.triggered.connect(self.manual_refresh)
		menu_tools.addAction(act_refresh)

		act_analysis = QAction("Data Analysis Toolkit", self)
		act_analysis.setShortcut(QKeySequence("A"))
		act_analysis.triggered.connect(self.open_analysis_toolkit)
		menu_tools.addAction(act_analysis)

		menu_tools.addSeparator()

		act_settings = QAction("Settings...", self)
		act_settings.setShortcut(QKeySequence("Ctrl+,"))
		act_settings.triggered.connect(self.open_settings_dialog)
		menu_tools.addAction(act_settings)

		# Ensure hotkeys trigger even when the menubar is hidden in fullscreen
		for act in [act_open_folder, act_backup, act_load_sess, act_save_sess,
					act_clear_data, act_export, act_charts, act_presets,
					self.act_fullscreen, self.act_stats_mode, self.act_year_offset,
					self.act_density, self.act_log_scale, self.act_moving_avg,
					act_refresh, act_analysis, act_settings]:
			self.addAction(act)

	def _build_ui(self):
		self.central_widget = QWidget()
		self.setCentralWidget(self.central_widget)
		self.layout = QVBoxLayout(self.central_widget)

		self.fig, self.ax = plt.subplots()
		self.fig.subplots_adjust(
			top=POS_SUBPLOT_TOP_EDGE,
			bottom=POS_SUBPLOT_BOTTOM_EDGE,
			left=POS_SUBPLOT_LEFT_EDGE,
			right=POS_SUBPLOT_RIGHT_EDGE,
			hspace=POS_SUBPLOT_HSPACE,
			wspace=POS_SUBPLOT_WSPACE
		)

		self.plot_container = QHBoxLayout()
		self.canvas = FigureCanvas(self.fig)
		self.plot_container.addWidget(self.canvas, stretch=4)

		self.stats_panel = QTextEdit()
		self.stats_panel.setReadOnly(True)
		self.stats_panel.setFixedWidth(STATS_PANEL_WIDTH)
		self.stats_panel.setStyleSheet("""
			QTextEdit {
				background-color: #1e1e1e; color: #e0e0e0;
				border: 1px solid #3c3c3c; border-radius: 4px;
				font-family: Consolas, 'Courier New', monospace; font-size: 12px;
				padding: 8px; line-height: 1.4;
			}
		""")
		self.stats_panel.setVisible(self.is_stats_mode)
		self.plot_container.addWidget(self.stats_panel, stretch=1)
		self.layout.addLayout(self.plot_container, 1)

		self.toolbar = NavigationToolbar(self.canvas, self)
		self.layout.addWidget(self.toolbar)

		# Controls
		self.top_button_layout = QHBoxLayout()
		self.btn_charts = QPushButton("Charts [`]")
		self.btn_preset_config = QPushButton("[P]resets")
		self.btn_refresh = QPushButton("Refresh [Ctrl+R]")
		self.btn_refresh.setToolTip("Reload log files from disk and re-render immediately [Ctrl+R]")

		self.btn_find = QPushButton("Find [Ctrl+F]")
		self.btn_find.setToolTip("Quick search all dropdown values in the current chart [Ctrl+F]")
		self.btn_find.clicked.connect(self.open_filter_search)

		self.btn_stats_mode = QPushButton("Stats mode [T]")
		self.btn_stats_mode.setCheckable(True)
		self.btn_stats_mode.setChecked(self.is_stats_mode)

		self.btn_year_offset = QPushButton("Relative year [Y]")
		self.btn_year_offset.setCheckable(True)
		self.btn_year_offset.setChecked(self.is_year_offset)
		self.btn_year_offset.setToolTip("Toggle time axis between absolute & relative [Y]")

		self.combo_stats_hide = QComboBox()
		self.combo_stats_hide.addItems([
			"Hide: None",
			"Hide: Min / Max",
			"Hide: Min/Max & 99th/1st",
			"Hide: Min/Max, 99th/1st, 95th/5th"
		])
		if 0 <= self.stats_hide_idx < self.combo_stats_hide.count():
			self.combo_stats_hide.setCurrentIndex(self.stats_hide_idx)
		self.combo_stats_hide.setVisible(self.is_stats_mode)
		self.combo_stats_hide.setToolTip("Select outliers/percentile bands to hide from the chart.")
		self.combo_stats_hide.currentIndexChanged.connect(self._on_stats_hide_changed)

		self.btn_density = QPushButton("Density [D]")
		self.btn_density.setCheckable(True)
		self.btn_density.setChecked(self.is_density)
		self.btn_density.setToolTip("Divides values by the number of locations.")

		self.btn_log_scale = QPushButton("[L]og scale")
		self.btn_log_scale.setCheckable(True)
		self.btn_log_scale.setChecked(self.is_log_scale)

		self.btn_moving_avg = QPushButton("Moving avg [W]")
		self.btn_moving_avg.setCheckable(True)
		self.btn_moving_avg.setChecked(self.is_moving_average)
		self.btn_moving_avg.setVisible(not(self.is_stats_mode))

		for w in [self.btn_charts, self.btn_preset_config, self.btn_find, self.btn_refresh,
				  self.btn_stats_mode, self.btn_year_offset, self.btn_density,
				  self.btn_log_scale, self.btn_moving_avg, self.combo_stats_hide]:
			self.top_button_layout.addWidget(w)

		self.top_button_layout.addStretch(1)
		self.layout.addLayout(self.top_button_layout)

		self.preset_button_layout = QHBoxLayout()
		self.layout.addLayout(self.preset_button_layout)

		self.filter_layout = QGridLayout()
		self.layout.addLayout(self.filter_layout)

		# Wire UI Events
		self.btn_refresh.clicked.connect(self.manual_refresh)
		self.btn_preset_config.clicked.connect(self.open_preset_config)
		self.btn_charts.clicked.connect(self.show_chart_list)
		self.btn_log_scale.toggled.connect(self.act_log_scale.setChecked)
		self.btn_moving_avg.toggled.connect(self.act_moving_avg.setChecked)
		self.btn_stats_mode.toggled.connect(self.act_stats_mode.setChecked)
		self.btn_year_offset.toggled.connect(self.act_year_offset.setChecked)
		self.btn_density.toggled.connect(self.act_density.setChecked)

	def setup_shortcuts(self):
		# Keyboard shortcuts are already handled by QAction shortcuts in the menu bar.

		# Hotkeys to step metric/category backward and forward
		self.sc_prev_metric = QShortcut(QKeySequence(","), self)
		self.sc_prev_metric.activated.connect(self.select_previous_metric)

		self.sc_next_metric = QShortcut(QKeySequence("."), self)
		self.sc_next_metric.activated.connect(self.select_next_metric)

		# Hotkeys to navigate preset pages
		self.sc_prev_preset_page = QShortcut(QKeySequence("Left"), self)
		self.sc_prev_preset_page.activated.connect(self._prev_preset_page)

		self.sc_next_preset_page = QShortcut(QKeySequence("Right"), self)
		self.sc_next_preset_page.activated.connect(self._next_preset_page)

	def _on_stats_hide_changed(self, idx):
		self.stats_hide_idx = idx
		self.save_app_settings()
		self.redraw_current_plot()

	def toggle_fullscreen(self, checked):
		self.menuBar().setVisible(not checked)
		if checked:
			self.showFullScreen()
		else:
			self.showNormal()

	def open_appdata_folder(self):
		QDesktopServices.openUrl(QUrl.fromLocalFile(APPDATA_DIR))

	def open_settings_dialog(self):
		dlg = SettingsDialog(self.refresh_interval_idx, self.autosave_interval_idx, self.period_value,
							 self.stats_shading_all, self)
		if dlg.exec():
			vals = dlg.get_settings()
			self.refresh_interval_idx = vals["refresh_idx"]
			self.autosave_interval_idx = vals["autosave_idx"]
			self.period_value = vals["period"]
			shading_changed = (self.stats_shading_all != vals["stats_shading_all"])
			self.stats_shading_all = vals["stats_shading_all"]
			if hasattr(self, 'act_stats_shading_all'):
				self.act_stats_shading_all.setChecked(self.stats_shading_all)

			self._apply_refresh_interval()
			self._apply_autosave_interval()
			self.save_app_settings()

			if self.is_moving_average or shading_changed:
				self.redraw_current_plot()

	def _apply_refresh_interval(self):
		intervals = [10, 30, 60, 300, 600, 0]
		ms = intervals[self.refresh_interval_idx] * 1000
		if ms == 0:
			self.timer_graph_refresh.stop()
		else:
			self.timer_graph_refresh.setInterval(ms)
			self.timer_graph_refresh.start()

	def _apply_autosave_interval(self):
		intervals = [60, 300, 600, 0]
		ms = intervals[self.autosave_interval_idx] * 1000
		if ms == 0:
			self.timer_auto_save.stop()
		else:
			self.timer_auto_save.setInterval(ms)
			self.timer_auto_save.start()

	def load_graph_definitions(self):
		registered = {
			'Building Types by Region': {'func': chart_library.graph_building_types, 'config': configs.BT_CONFIG},
			'Goods Prices by Region': {'func': chart_library.graph_goods_prices, 'config': configs.GP_CONFIG},
			'Market Statistics': {'func': chart_library.graph_markets, 'config': configs.MK_CONFIG},
			'Population by Region': {'func': chart_library.graph_population, 'config': configs.POP_CONFIG},
			'Road Coverage by Region': {'func': chart_library.graph_road_types, 'config': configs.RT_CONFIG},
			'Country Metrics': {'func': chart_library.graph_country_metrics, 'config': configs.CM_CONFIG},
			'Credit Statistics': {'func': chart_library.graph_credit, 'config': configs.CR_CONFIG},
		}
		self.graphs = registered
		self.chart_shortcuts.clear()
		for idx, chart_name in enumerate(sorted(self.graphs.keys())):
			hotkey = f"F{idx + 1}"
			self.chart_hotkeys[hotkey] = chart_name
			sc = QShortcut(QKeySequence(hotkey), self)
			sc.activated.connect(partial(self.plot_by_hotkey, hotkey))
			self.chart_shortcuts.append(sc)

	def plot_by_hotkey(self, key):
		name = self.chart_hotkeys.get(key)
		if name and name in self.graphs:
			self.display_chart(self.graphs[name], name)

	def display_info_screen(self, msg=None):
		self.cursor_hover_handler = None
		self._reset_filter_layout()
		self.clear_preset_buttons()
		self.current_preset_chart = None
		self.ax.clear()
		self.fig.suptitle(None)
		self.ax.set_title("Menu")
		self.ax.text(0.5, 0.5, msg if msg else GRAPH_INTRODUCTION.strip(), ha="center", va="center")
		self.canvas.draw()
		self.current_graph_info = None

	def _save_current_filters_to_memory(self):
		if self.current_graph_info:
			title = self.current_graph_info['title']
			self.chart_filter_memory[title] = {
				k: w.currentText() for k, w in self.filter_widget_map.items() if isinstance(w, QComboBox)
			}

	def display_chart(self, graph_info, title, preserve_toggles=False):
		self._save_current_filters_to_memory()

		self.current_graph_info = {'info': graph_info, 'title': title}
		if not preserve_toggles:
			self.is_log_scale = False
			self.btn_log_scale.setChecked(False)
			self.act_log_scale.setChecked(False)
			self.is_moving_average = False
			self.btn_moving_avg.setChecked(False)
			self.act_moving_avg.setChecked(False)
			self.is_density = False
			self.btn_density.setChecked(False)
			self.act_density.setChecked(False)

		self.btn_density.setVisible(True)
		self.btn_density.setEnabled(True)

		self._reset_filter_layout()
		self.ax.clear()
		self.fig.suptitle(title)
		self.fig.subplots_adjust(
			top=POS_SUBPLOT_TOP_EDGE,
			bottom=POS_SUBPLOT_BOTTOM_EDGE,
			left=POS_SUBPLOT_LEFT_EDGE,
			right=POS_SUBPLOT_RIGHT_EDGE,
			hspace=POS_SUBPLOT_HSPACE,
			wspace=POS_SUBPLOT_WSPACE
		)

		try:
			graph_info['func'](
				self.data, self.ax, self.filter_layout, self.filter_widgets,
				self.on_plot_updated, self.clear_tooltip_handler, self.filter_widget_map,
				lambda: self.is_moving_average, lambda: self.period_value,
				lambda: self.is_stats_mode, self.update_stats_summary_panel,
				lambda: 9, set_redraw_fn=self.set_redraw_fn,
				get_is_density=lambda: self.is_density,
				get_stats_hide_level=lambda: self.combo_stats_hide.currentIndex(),
				get_stats_shading_all=lambda: self.stats_shading_all,
				get_is_year_offset=lambda: self.is_year_offset
			)
			for combo in self.filter_widget_map.values():
				if isinstance(combo, QComboBox):
					combo.currentIndexChanged.connect(self._save_current_filters_to_memory)

			self.canvas.draw()
			self.setup_preset_buttons(title)
			self._restore_filters(title)
			self.redraw_current_plot()
		except Exception as e:
			self.ax.text(0.5, 0.5, f"Error:\n{e}", ha='center', va='center')

		self.canvas.draw()

	def clear_log_files_on_disk(self) -> int:
		"""Empties the active error.log and rotated error.*.log files on disk."""
		target_files = set(self.get_all_log_files())
		target_files.add(os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}.log"))
		for i in range(1, 6):
			target_files.add(os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}.{i}.log"))

		cleared_files_count = 0
		for filepath in target_files:
			if os.path.exists(filepath):
				try:
					with open(filepath, 'w', encoding='utf-8'):
						pass
					cleared_files_count += 1
				except (IOError, PermissionError) as e:
					print(f"Could not clear file {filepath}: {e}")
		return cleared_files_count

	def handle_column_mismatch(self, got_count, expected_count):
		"""Asks user whether to wipe error logs when a column count mismatch occurs."""
		if self._handling_mismatch:
			return
		self._handling_mismatch = True
		try:
			reply = QMessageBox.question(
				self,
				"Column Count Mismatch",
				f"Column count mismatch detected in country logs:\n"
				f"Got {got_count} columns, expected {expected_count}.\n\n"
				"This usually indicates incompatible or corrupted logs from another version.\n\n"
				"Do you want to clear the error logs on disk?",
				QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
				QMessageBox.StandardButton.Yes
			)
			if reply == QMessageBox.StandardButton.Yes:
				cleared_count = self.clear_log_files_on_disk()
				self.data = ""
				self.logs = []
				self.chart_filter_memory.clear()
				self.has_new_data = False
				log_parser.reset_cumulative_history()
				self.stats_panel.clear()
				self._update_last_log_state()
				self.display_info_screen(f"Emptied {cleared_count} log file(s) due to mismatch.\nPlay more or refresh to reload.")
		finally:
			self._handling_mismatch = False

	def clear_data(self):
		msg_box = QMessageBox(self)
		msg_box.setWindowTitle("Clear Data")
		msg_box.setText("Choose how you want to clear the data:")

		btn_clear_both = msg_box.addButton("Clear app data and log files", QMessageBox.ButtonRole.DestructiveRole)
		btn_clear_app = msg_box.addButton("Clear app data only", QMessageBox.ButtonRole.AcceptRole)
		btn_cancel = msg_box.addButton(QMessageBox.StandardButton.Cancel)

		msg_box.exec()
		clicked = msg_box.clickedButton()

		if clicked == btn_cancel or clicked is None:
			return

		# Reset application in-memory stores and caches
		self.data = ""
		self.logs = []
		self.chart_filter_memory.clear()
		self.has_new_data = False
		log_parser.reset_cumulative_history()
		self.stats_panel.clear()

		# If requested, clear the contents of error.log and the 5 rotated files (error.1.log to error.5.log)
		cleared_files_count = 0
		if clicked == btn_clear_both:
			cleared_files_count = self.clear_log_files_on_disk()

		self._update_last_log_state()

		status_msg = (
			f"App data cleared and contents of {cleared_files_count} log file(s) emptied."
			if clicked == btn_clear_both
			else "App data cleared."
		)
		self.display_info_screen(f"{status_msg}\nPlay more or refresh to reload.")

	def _restore_filters(self, title):
		for widget in self.filter_widget_map.values():
			widget.blockSignals(True)
		try:
			if title in self.chart_filter_memory:
				for k, val in self.chart_filter_memory[title].items():
					target_key = k
					if target_key not in self.filter_widget_map:
						if target_key == 'region' and 'country' in self.filter_widget_map:
							target_key = 'country'
						elif target_key == 'region' and 'market' in self.filter_widget_map:
							target_key = 'market'
						elif target_key == 'metric' and 'credit_metric' in self.filter_widget_map:
							target_key = 'credit_metric'
					if target_key in self.filter_widget_map:
						idx = self.filter_widget_map[target_key].findText(val)
						if idx != -1: self.filter_widget_map[target_key].setCurrentIndex(idx)
			elif title in self.key_configs and self.key_configs[title]:
				sorted_keys = sort_hotkeys(self.key_configs[title].keys())
				first_preset = self.key_configs[title][sorted_keys[0]]
				for k, val in first_preset.get("filters", {}).items():
					target_key = k
					if target_key not in self.filter_widget_map:
						if target_key == 'region' and 'country' in self.filter_widget_map:
							target_key = 'country'
						elif target_key == 'region' and 'market' in self.filter_widget_map:
							target_key = 'market'
						elif target_key == 'metric' and 'credit_metric' in self.filter_widget_map:
							target_key = 'credit_metric'
					if target_key in self.filter_widget_map:
						idx = self.filter_widget_map[target_key].findText(val)
						if idx != -1: self.filter_widget_map[target_key].setCurrentIndex(idx)
		finally:
			for widget in self.filter_widget_map.values():
				widget.blockSignals(False)

	def _reset_filter_layout(self):
		for w in self.filter_widgets:
			self.filter_layout.removeWidget(w)
			w.deleteLater()
		self.filter_widgets.clear()
		self.filter_widget_map.clear()

		while self.filter_layout.count():
			item = self.filter_layout.takeAt(0)
			if item.widget():
				item.widget().deleteLater()
		self.layout.removeItem(self.filter_layout)
		self.filter_layout.deleteLater()

		self.filter_layout = QGridLayout()
		self.layout.addLayout(self.filter_layout)

	def set_redraw_fn(self, fn):
		self.current_redraw_fn = fn

	def redraw_current_plot(self):
		if callable(self.current_redraw_fn):
			self.current_redraw_fn()
		self.apply_plot_settings()

	def on_plot_updated(self):
		self.cursor_hover_handler = InteractiveLineTooltip(
			self.ax,
			on_line_click_callback=self.handle_line_click,
			on_stats_hover_callback=self.update_stats_summary_panel
		)
		self.cursor_hover_handler.setup_tooltip_handler()
		self.apply_plot_settings()

	def clear_tooltip_handler(self):
		self.cursor_hover_handler = None

	def handle_line_click(self, line_label):
		if not self.current_graph_info or self.is_stats_mode:
			return

		cat_k = self.current_graph_info['info']['config']['category_key']
		entity_k = self.current_graph_info['info']['config'].get('entity_key', 'region')
		c_combo = self.filter_widget_map.get(cat_k)
		r_combo = self.filter_widget_map.get(entity_k)
		if not c_combo or not r_combo:
			return

		for combo in (c_combo, r_combo):
			combo.blockSignals(True)
		try:
			all_cat = self.current_graph_info['info']['config'].get('all_category_str')
			if (c_combo.currentIndex() != 0 or all_cat is None) and r_combo.currentIndex() == 0:
				idx = r_combo.findText(line_label)
				if idx != -1:
					r_combo.setCurrentIndex(idx)
					if all_cat:
						c_combo.setCurrentIndex(0)
			elif r_combo.currentIndex() != 0 and (c_combo.currentIndex() == 0 and all_cat):
				idx = c_combo.findText(line_label)
				if idx != -1:
					c_combo.setCurrentIndex(idx)
					r_combo.setCurrentIndex(0)
		finally:
			for combo in (c_combo, r_combo):
				combo.blockSignals(False)
		self.redraw_current_plot()

	def update_stats_summary_panel(self, global_stats, year_stats=None):
		if not global_stats or not self.is_stats_mode:
			self.stats_panel.clear()
			return
		self.stats_panel.setPlainText(
			format_stats_panel_text(global_stats, year_stats, is_year_offset=self.is_year_offset)
		)

	def toggle_stats_mode(self, checked):
		self.is_stats_mode = checked
		self.btn_stats_mode.setChecked(checked)
		self.act_stats_mode.setChecked(checked)
		self.stats_panel.setVisible(checked)
		self.combo_stats_hide.setVisible(checked)
		self.btn_moving_avg.setVisible(checked)
		self.act_moving_avg.setVisible(checked)
		self.save_app_settings()
		self.redraw_current_plot()

	def toggle_year_offset(self, checked):
		self.is_year_offset = checked
		self.btn_year_offset.setChecked(checked)
		self.act_year_offset.setChecked(checked)
		self.save_app_settings()
		self.redraw_current_plot()

	def toggle_stats_shading_all(self, checked):
		self.stats_shading_all = checked
		if hasattr(self, 'act_stats_shading_all'):
			self.act_stats_shading_all.setChecked(checked)
		self.save_app_settings()
		if self.is_stats_mode:
			self.redraw_current_plot()

	def toggle_density(self, checked):
		if checked:
			rloc_map = log_parser.get_region_locations()
			has_country_locs = any(
				(r.get("locations", 0) or r.get("num_locations", 0) or 0) > 0
				for r in log_parser.tg_cumulative_store.values()
			)
			has_region_locs = bool(rloc_map and any(v > 0 for v in rloc_map.values()))
			has_market_locs = any(
				(r.get("locations", 0) or 0) > 0
				for r in log_parser.mk_cumulative_store.values()
			)

			is_country = bool(self.current_graph_info and self.current_graph_info['title'] in ("Country Metrics", "Credit Statistics"))
			is_market = bool(self.current_graph_info and self.current_graph_info['title'] == "Market Statistics")

			if is_country:
				has_locs = has_country_locs
			elif is_market:
				has_locs = has_market_locs
			else:
				has_locs = has_region_locs

			if not has_locs:
				QMessageBox.warning(
					self,
					"No Location Data",
					"There is no count of locations stored in the loaded logs.\n\n"
					"Density calculation requires location counts."
				)
				self.btn_density.setChecked(False)
				self.act_density.setChecked(False)
				self.is_density = False
				return

		self.is_density = checked
		self.btn_density.setChecked(checked)
		self.act_density.setChecked(checked)
		self.save_app_settings()
		self.redraw_current_plot()

	def toggle_log_scale(self, checked):
		self.is_log_scale = checked
		self.btn_log_scale.setChecked(checked)
		self.act_log_scale.setChecked(checked)
		self.save_app_settings()
		self.apply_plot_settings()

	def toggle_moving_average(self, checked):
		self.is_moving_average = checked
		self.btn_moving_avg.setChecked(checked)
		self.act_moving_avg.setChecked(checked)
		self.save_app_settings()
		self.redraw_current_plot()

	def apply_plot_settings(self):
		if not (self.ax.get_lines() or self.ax.patches):
			return
		try:
			if self.is_log_scale:
				has_negative = False
				for line in self.ax.get_lines():
					y = line.get_ydata()
					if len(y) > 0 and np.any(np.asarray(y) < 0):
						has_negative = True
						break
				if not has_negative:
					for p in self.ax.patches:
						if p.get_y() < 0 or (p.get_height() is not None and p.get_height() < 0):
							has_negative = True
							break

				if has_negative:
					self.ax.set_yscale('symlog')
				else:
					self.ax.set_yscale('log', nonpositive='clip')
			else:
				self.ax.set_yscale('linear')
			self.canvas.draw_idle()
		except Exception:
			self.is_log_scale = False
			self.btn_log_scale.setChecked(False)
			self.act_log_scale.setChecked(False)
			self.ax.set_yscale('linear')
			self.canvas.draw_idle()

	def show_chart_list(self):
		dlg = ChartSelectionDialog(self.graphs, self.chart_hotkeys, self)
		if dlg.exec() and dlg.selected_chart:
			self.display_chart(self.graphs[dlg.selected_chart], dlg.selected_chart)

	def load_key_configs(self):
		# Migrate local key_configs.json if it exists and appdata one does not
		if os.path.exists("key_configs.json") and not os.path.exists(KEY_CONFIGS_PATH):
			try:
				shutil.copy("key_configs.json", KEY_CONFIGS_PATH)
			except Exception:
				pass

		if os.path.exists(KEY_CONFIGS_PATH):
			try:
				with open(KEY_CONFIGS_PATH, "r", encoding="utf-8") as f:
					self.key_configs = json.load(f)
			except Exception as e:
				QMessageBox.critical(self, "Config Error", f"Error in {KEY_CONFIGS_PATH}: {e}")
		elif os.path.exists("key_configs.json"):
			try:
				with open("key_configs.json", "r", encoding="utf-8") as f:
					self.key_configs = json.load(f)
			except Exception as e:
				QMessageBox.critical(self, "Config Error", f"Error in key_configs.json: {e}")

	def save_key_configs(self):
		try:
			with open(KEY_CONFIGS_PATH, "w", encoding="utf-8") as f:
				json.dump(self.key_configs, f, indent=2)
		except Exception as e:
			QMessageBox.critical(self, "Config Error", f"Error saving {KEY_CONFIGS_PATH}: {e}")

	def open_preset_config(self):
		if not self.current_graph_info:
			QMessageBox.information(self, "No Chart Active", "Please select a chart first before assigning preset hotkeys.")
			self.show_chart_list()
			return
		chart_title = self.current_graph_info['title']
		dlg = PresetConfigDialog(chart_title, self.filter_widget_map, self.key_configs, self)
		if dlg.exec():
			self.save_key_configs()
			self.setup_preset_buttons(chart_title)

	def setup_preset_buttons(self, chart_title):
		self.clear_preset_buttons()
		self.current_preset_chart = chart_title
		self.preset_page = 0
		cfgs = self.key_configs.get(chart_title, {})

		# Keep all hotkeys active globally regardless of which page is visible
		for key in sort_hotkeys(cfgs.keys()):
			cfg = cfgs[key]
			sc = QShortcut(QKeySequence(key), self)
			sc.activated.connect(partial(self._apply_preset_filter, cfg.get("filters", {})))
			self.preset_shortcuts.append(sc)

		self._render_preset_buttons()

	def _render_preset_buttons(self):
		# Clear existing layout widgets without clearing global QShortcuts
		while self.preset_button_layout.count():
			item = self.preset_button_layout.takeAt(0)
			if item.widget():
				item.widget().deleteLater()
		self.preset_buttons.clear()

		if not getattr(self, 'current_preset_chart', None):
			return

		cfgs = self.key_configs.get(self.current_preset_chart, {})
		sorted_keys = sort_hotkeys(cfgs.keys())
		total_presets = len(sorted_keys)

		if total_presets == 0:
			return

		total_pages = max(1, (total_presets + PRESETS_PER_PAGE - 1) // PRESETS_PER_PAGE)
		if self.preset_page >= total_pages:
			self.preset_page = total_pages - 1
		elif self.preset_page < 0:
			self.preset_page = 0

		start_idx = self.preset_page * PRESETS_PER_PAGE
		end_idx = min(start_idx + PRESETS_PER_PAGE, total_presets)
		page_keys = sorted_keys[start_idx:end_idx]

		for key in page_keys:
			cfg = cfgs[key]
			btn = QPushButton(f"{cfg.get('description', '')} [{key}]")
			btn.clicked.connect(partial(self._apply_preset_filter, cfg.get("filters", {})))
			self.preset_button_layout.addWidget(btn)
			self.preset_buttons.append(btn)

		self.preset_button_layout.addStretch(1)

		if total_pages > 1:
			btn_prev = QPushButton("◀")
			btn_prev.setToolTip("Previous preset page [Alt+Left]")
			btn_prev.setFixedWidth(32)
			btn_prev.clicked.connect(self._prev_preset_page)

			lbl_page = QLabel(f"Page {self.preset_page + 1}/{total_pages}")
			lbl_page.setStyleSheet("font-weight: bold; padding: 0 4px;")

			btn_next = QPushButton("▶")
			btn_next.setToolTip("Next preset page [Alt+Right]")
			btn_next.setFixedWidth(32)
			btn_next.clicked.connect(self._next_preset_page)

			self.preset_button_layout.addWidget(btn_prev)
			self.preset_button_layout.addWidget(lbl_page)
			self.preset_button_layout.addWidget(btn_next)

	def _prev_preset_page(self):
		if not getattr(self, 'current_preset_chart', None):
			return
		cfgs = self.key_configs.get(self.current_preset_chart, {})
		total_pages = max(1, (len(cfgs) + PRESETS_PER_PAGE - 1) // PRESETS_PER_PAGE)
		if total_pages <= 1:
			return
		self.preset_page = (self.preset_page - 1) % total_pages
		self._render_preset_buttons()

	def _next_preset_page(self):
		if not getattr(self, 'current_preset_chart', None):
			return
		cfgs = self.key_configs.get(self.current_preset_chart, {})
		total_pages = max(1, (len(cfgs) + PRESETS_PER_PAGE - 1) // PRESETS_PER_PAGE)
		if total_pages <= 1:
			return
		self.preset_page = (self.preset_page + 1) % total_pages
		self._render_preset_buttons()
	def _apply_preset_filter(self, filters):
		for combo in self.filter_widget_map.values():
			combo.blockSignals(True)
		try:
			for k, v in filters.items():
				target_key = k
				if target_key not in self.filter_widget_map:
					if target_key == 'region' and 'country' in self.filter_widget_map:
						target_key = 'country'
					elif target_key == 'region' and 'market' in self.filter_widget_map:
						target_key = 'market'
					elif target_key == 'metric' and 'credit_metric' in self.filter_widget_map:
						target_key = 'credit_metric'
				if target_key in self.filter_widget_map:
					idx = self.filter_widget_map[target_key].findText(v)
					if idx != -1: self.filter_widget_map[target_key].setCurrentIndex(idx)
		finally:
			for combo in self.filter_widget_map.values():
				combo.blockSignals(False)
		self.redraw_current_plot()

	def clear_preset_buttons(self):
		while self.preset_button_layout.count():
			item = self.preset_button_layout.takeAt(0)
			if item.widget():
				item.widget().deleteLater()
		self.preset_buttons.clear()
		for sc in self.preset_shortcuts:
			sc.deleteLater()
		self.preset_shortcuts.clear()

	def get_all_log_files(self):
		file_list = []
		rotated = glob.glob(os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}.*.log"))
		if rotated:
			def log_num(path):
				n = re.findall(r'\.(\d+)\.log$', os.path.basename(path))
				return int(n[0]) if n else -1
			rotated.sort(key=log_num, reverse=True)
			file_list.extend(rotated)

		manual = glob.glob(os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}_*.log"))
		if manual:
			manual.sort(key=lambda x: int(re.findall(r'\d+', os.path.basename(x))[-1]))
			file_list.extend(manual)

		active = os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}.log")
		if os.path.exists(active):
			file_list.append(active)
		return file_list

	def read_all_logs(self):
		files = self.get_all_log_files()
		chunks = []
		for fn in files:
			try:
				with open(fn, "r", encoding="utf-8", errors="replace") as f:
					chunks.append(f.read())
			except (IOError, PermissionError) as e:
				print(f"Log read warning: {e}")
		return files, "".join(chunks)

	def read_and_parse_logs(self, force_all=False):
		"""Incrementally reads and streams log files, to avoid freezing."""
		files = self.get_all_log_files()
		if force_all:
			log_parser.reset_cumulative_history()

		modified_any = False
		for fn in files:
			if force_all or log_parser.should_parse_file(fn):
				log_parser.parse_log_file(fn)
				modified_any = True

		if modified_any:
			log_parser.clear_all_caches()
			self.data = "loaded"

		self.logs = files

	def check_log_updates(self):
		"""Inspects disk files and ingests only modified ones."""
		files = self.get_all_log_files()
		if not files:
			return

		needs_parsing = any(log_parser.should_parse_file(fn) for fn in files)
		if needs_parsing:
			self.read_and_parse_logs(force_all=False)
			self._update_last_log_state()
			self.has_new_data = True

	def manual_refresh(self):
		"""Forces re-reading of log files and re-renders the current chart."""
		self.read_and_parse_logs(force_all=True)
		self._update_last_log_state()
		self.has_new_data = False
		if self.current_graph_info:
			self.display_chart(
				self.current_graph_info['info'],
				self.current_graph_info['title'],
				preserve_toggles=True
			)
		else:
			self.display_info_screen()

	def _update_last_log_state(self):
		cur = []
		for f in self.get_all_log_files():
			try:
				s = os.stat(f)
				cur.append((f, s.st_size, s.st_mtime))
			except OSError:
				pass
		self.last_log_state = cur

	def reload_log(self, is_interactive=True):
		saved_info = self.current_graph_info
		self.read_and_parse_logs()
		self._update_last_log_state()
		self.has_new_data = False

		if is_interactive and not self.logs:
			if QMessageBox.warning(self, "No Logs", f"No logs in {self.log_folder}.\nChange?",
								   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
				self.change_log_folder()
				return

		if saved_info:
			self.display_chart(saved_info['info'], saved_info['title'], preserve_toggles=True)
		else:
			self.display_info_screen()

	def manual_refresh(self):
		"""Forces an immediate read of all log files and re-renders the current chart."""
		self.reload_log(is_interactive=True)

	def check_log_updates(self):
		"""Runs every 5 seconds to inspect files on disk and ingest changes."""
		files = self.get_all_log_files()
		if not files:
			return
		cur = []
		for f in files:
			try:
				s = os.stat(f)
				cur.append((f, s.st_size, s.st_mtime))
			except OSError:
				return

		if self.last_log_state is None:
			self.last_log_state = cur
			return

		if cur != self.last_log_state:
			self.last_log_state = cur
			self.read_and_parse_logs()
			self.has_new_data = True

	def auto_refresh_graph(self):
		"""Re-renders current chart when new data has arrived."""
		if not self.has_new_data:
			return
		self.has_new_data = False
		if self.current_graph_info:
			self.display_chart(
				self.current_graph_info['info'],
				self.current_graph_info['title'],
				preserve_toggles=True
			)

	def backup_log(self):
		if not self.logs: return
		nums = re.findall(r'\d+', self.logs[-1])
		nxt = int(nums[0]) + 1 if nums else 1
		src = os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}.log")
		dst = os.path.join(self.log_folder, f"{TARGET_FILE_NAME_ROOT}_{nxt}.log")
		try:
			os.rename(src, dst)
			QMessageBox.information(self, "Backed Up", f"Moved to {TARGET_FILE_NAME_ROOT}_{nxt}.log")
		except Exception as e:
			QMessageBox.critical(self, "Backup Error", str(e))

	def change_log_folder(self):
		new_path = QFileDialog.getExistingDirectory(self, "Select Log Folder", self.log_folder)
		if new_path and new_path != self.log_folder:
			self.log_folder = new_path
			fetch_logs.update_config_file('Paths', 'log_directory', new_path)
			self.reload_log()

	def find_most_recent_autosave(self):
		"""Finds the most recent autosave / session file across all locations."""
		candidates = []
		# Check AUTOSAVE_DIR
		if os.path.exists(AUTOSAVE_DIR):
			candidates.extend(glob.glob(os.path.join(AUTOSAVE_DIR, "*.dat")))
		# Check current working directory
		candidates.extend(glob.glob("*.dat"))

		valid_files = [f for f in set(candidates) if os.path.isfile(f) and os.path.getsize(f) > 0]
		if not valid_files:
			return None
		valid_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
		return valid_files[0]

	def load_initial_data(self):
		recent_save = self.find_most_recent_autosave()
		if recent_save:
			mod_time = datetime.fromtimestamp(os.path.getmtime(recent_save)).strftime("%Y-%m-%d %H:%M")
			file_label = os.path.basename(recent_save)
			msg_box = QMessageBox(self)
			msg_box.setWindowTitle("Restore Session?")
			msg_box.setText(f"Most recent saved session found:\n{file_label} ({mod_time})\n\nRestore?")
			btn_yes = msg_box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
			btn_no = msg_box.addButton("No", QMessageBox.ButtonRole.NoRole)
			btn_no_clear = msg_box.addButton("No, and clear error logs", QMessageBox.ButtonRole.DestructiveRole)
			msg_box.setDefaultButton(btn_yes)
			msg_box.exec()
			clicked = msg_box.clickedButton()

			if clicked == btn_yes:
				if self.load_session_file(recent_save):
					return
			elif clicked == btn_no_clear:
				self.clear_log_files_on_disk()
				self.reload_log(is_interactive=True)
				return

		self.reload_log(is_interactive=True)

	def manual_save(self):
		path, _ = QFileDialog.getSaveFileName(self, "Save Session", "session_backup.dat", "Session Data (*.dat)")
		if path:
			self._save_current_filters_to_memory()
			title = self.current_graph_info['title'] if self.current_graph_info else None
			ok = save_session(path, self.data, self.logs, self.chart_filter_memory, title)
			QMessageBox.information(self, "Saved", "Session saved successfully!" if ok else "Save failed.")

	def manual_load(self):
		path, _ = QFileDialog.getOpenFileName(self, "Load Session", "", "Session Data (*.dat);;All Files (*.*)")
		if path:
			self.load_session_file(path)

	def load_session_file(self, filepath):
		session = load_session(filepath)
		if not session:
			return False
		self.data = session.get("data", "")
		self.logs = session.get("logs", [])
		self.chart_filter_memory = session.get("chart_filter_memory", {})
		self.has_new_data = False
		self._update_last_log_state()
		cur = session.get("current_chart")
		if cur and cur in self.graphs:
			self.display_chart(self.graphs[cur], cur)
		else:
			self.display_info_screen("Session loaded.")
		return True

	def auto_save_data(self):
		if self.autosave_interval_idx != 3 and self.data:
			self._save_current_filters_to_memory()
			title = self.current_graph_info['title'] if self.current_graph_info else None

			# Save latest standard autosave file
			save_session(AUTOSAVE_FILE, self.data, self.logs, self.chart_filter_memory, title)

			# Also create timestamped autosave
			timestamp_file = os.path.join(AUTOSAVE_DIR, f"autosave_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dat")
			save_session(timestamp_file, self.data, self.logs, self.chart_filter_memory, title)

			# Prune older autosaves keeping the newest 20
			all_autosaves = sorted(glob.glob(os.path.join(AUTOSAVE_DIR, "autosave_*.dat")), key=os.path.getmtime)
			if len(all_autosaves) > AUTOSAVES_KEPT:
				for old_f in all_autosaves[:-AUTOSAVES_KEPT]:
					try:
						os.remove(old_f)
					except OSError:
						pass

	def open_analysis_toolkit(self):
		csv_path = os.path.join(self.log_folder, "csv_export", "country_stats.csv")
		if not os.path.exists(csv_path):
			if run_export_pipeline(self.data, self.log_folder, self):
				self.open_analysis_toolkit()
			return
		try:
			df = pd.read_csv(csv_path, low_memory=False)
			dlg = AnalysisToolkitDialog(df, self)
			dlg.exec()
		except Exception as e:
			QMessageBox.critical(self, "Analysis Toolkit Error", str(e))

	def closeEvent(self, event):
		self.save_app_settings()
		if not self.data or self.autosave_interval_idx == 3:
			event.accept()
			return
		reply = QMessageBox.question(self, "Save on Exit", "Save session before exit?",
									 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
		if reply == QMessageBox.StandardButton.Yes:
			title = self.current_graph_info['title'] if self.current_graph_info else None
			save_session(AUTOSAVE_FILE, self.data, self.logs, self.chart_filter_memory, title)
			event.accept()
		elif reply == QMessageBox.StandardButton.No:
			event.accept()
		else:
			event.ignore()

	def decrease_stats_hide(self):
		if hasattr(self, 'combo_stats_hide'):
			cur = self.combo_stats_hide.currentIndex()
			if cur > 0:
				self.combo_stats_hide.setCurrentIndex(cur - 1)

	def increase_stats_hide(self):
		if hasattr(self, 'combo_stats_hide'):
			cur = self.combo_stats_hide.currentIndex()
			if cur < self.combo_stats_hide.count() - 1:
				self.combo_stats_hide.setCurrentIndex(cur + 1)

	def _get_metric_combobox(self):
		"""Returns the primary metric/category combobox for the current chart."""
		if not self.current_graph_info:
			return None
		cat_key = self.current_graph_info['info']['config'].get('category_key')
		combo = self.filter_widget_map.get(cat_key)
		if isinstance(combo, QComboBox):
			return combo
		# Fallback to any metric-like key
		for key in ['country_metric', 'credit_metric', 'statistic', 'good', 'building', 'road_type']:
			w = self.filter_widget_map.get(key)
			if isinstance(w, QComboBox):
				return w
		return None

	def select_previous_metric(self):
		combo = self._get_metric_combobox()
		if combo and combo.count() > 0:
			new_idx = (combo.currentIndex() - 1) % combo.count()
			combo.setCurrentIndex(new_idx)

	def select_next_metric(self):
		combo = self._get_metric_combobox()
		if combo and combo.count() > 0:
			new_idx = (combo.currentIndex() + 1) % combo.count()
			combo.setCurrentIndex(new_idx)

	def open_filter_search(self):
		"""Opens Ctrl+F search dialog to quickly find and select dropdown options."""
		if not self.current_graph_info or not self.filter_widget_map:
			QMessageBox.information(self, "No Chart", "Please open a chart first to search its filters.")
			return

		dlg = FilterSearchDialog(self.filter_widget_map, self)
		if dlg.exec() and dlg.selected_target:
			combo, target_val = dlg.selected_target
			idx = combo.findText(target_val)
			if idx != -1:
				combo.setCurrentIndex(idx)
				self.redraw_current_plot()