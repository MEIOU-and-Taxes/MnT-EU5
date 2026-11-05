import json
import os
import shutil
from functools import partial

import pandas as pd
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QShortcut, QKeySequence, QIcon, QDesktopServices
from PyQt6.QtWidgets import (
	QMainWindow, QComboBox, QMessageBox,
	QApplication
)

import src.parsing.stores
from src.analysis_toolkit import AnalysisToolkitDialog
from src.constants import (
	REFRESH_PERIOD_MS, AUTOSAVE_PERIOD_MS, AUTOSAVE_FILE, APPDATA_DIR, KEY_CONFIGS_PATH,
	ICON_PATH, GRAPH_INTRODUCTION, POS_SUBPLOT_TOP_EDGE, POS_SUBPLOT_BOTTOM_EDGE,
	POS_SUBPLOT_LEFT_EDGE, POS_SUBPLOT_RIGHT_EDGE,
	POS_SUBPLOT_HSPACE, POS_SUBPLOT_WSPACE
)
from src.parsing import log_parser
from src.plotting import chart_library, configs
from src.services.exporter import run_export_pipeline
from src.services.session_manager import save_session
from src.services.settings_store import SettingsStore
from src.ui.filter_controller import FilterController
from src.ui.log_watcher import MainMenuLogWatcher
from src.ui.menu_builder import MenuBuilder
from src.ui.preset_bar import PresetBar
from src.ui.session_controller import SessionController
from src.ui.stats_panel import format_stats_panel_text
from src.ui.time_navigation import TimeNavigation
from src.ui.toolbar_builder import ToolbarBuilder
from src.ui.view_modes import ViewNodes
from src.widgets.chart_dialog import ChartSelectionDialog
from src.widgets.hotkey_utils import sort_hotkeys
from src.widgets.preset_dialog import PresetConfigDialog
from src.widgets.settings_dialog import SettingsDialog
from tools.shared.fetch_logs import get_from_config

class MainWindow(MenuBuilder, PresetBar, MainMenuLogWatcher, SettingsStore, FilterController,
				 TimeNavigation, SessionController, ToolbarBuilder, ViewNodes, QMainWindow):
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
		self.baseline_mode = "none"   # "none", "ratio", "difference"
		self.is_bar_chart = False
		self.is_stats_panel_visible = True
		self.density_mode = "none"    # "none", "location", "population"
		self.derivative_order = 0     # 0: Base, 1: Rate, 2: Acceleration
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
		QApplication.instance().installEventFilter(self)

		# Constant 1-second watcher: checks and reads log files from disk
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

	def set_density_mode(self, mode):
		if mode == "location":
			rloc_map = log_parser.get_region_locations()
			has_locs = any(v > 0 for v in rloc_map.values()) or any(
				(r.get("locations", 0) or r.get("num_locations", 0) or 0) > 0
				for r in src.parsing.stores.tg_cumulative_store.values()
			)
			if not has_locs:
				QMessageBox.warning(self, "No Location Data", "No location counts are stored in the current logs.")
				mode = "none"
		elif mode == "population":
			has_pop = (
				bool(src.parsing.stores.pop_cumulative_store)
				or any(float(r.get("Population", 0) or 0) > 0 for r in src.parsing.stores.tg_cumulative_store.values())
				or any(r.get("statistic") == "Population" and float(r.get("value", 0) or 0) > 0 for r in src.parsing.stores.mk_cumulative_store.values())
			)
			if not has_pop:
				QMessageBox.warning(self, "No Population Data", "No population data is stored in the current logs.")
				mode = "none"

		self.density_mode = mode
		density_idx_map = {"none": 0, "population": 1, "location": 2}
		target_idx = density_idx_map.get(mode, 0)
		if hasattr(self, 'combo_density') and self.combo_density.currentIndex() != target_idx:
			self.combo_density.blockSignals(True)
			self.combo_density.setCurrentIndex(target_idx)
			self.combo_density.blockSignals(False)

		if hasattr(self, 'act_density_loc'):
			self.act_density_loc.setChecked(mode == "location")
		if hasattr(self, 'act_density_pop'):
			self.act_density_pop.setChecked(mode == "population")
		self.save_app_settings()
		self.redraw_current_plot()

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
			'Country Metrics': {'func': chart_library.graph_country_metrics, 'config': configs.CM_CONFIG},
			'Market Statistics': {'func': chart_library.graph_markets, 'config': configs.MK_CONFIG},
			'Regional Statistics': {'func': chart_library.graph_regional_statistics, 'config': configs.REGIONAL_CONFIG},
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
			self.baseline_mode = "none"
			if hasattr(self, 'combo_baseline'):
				self.combo_baseline.blockSignals(True)
				self.combo_baseline.setCurrentIndex(0)
				self.combo_baseline.blockSignals(False)
			self.density_mode = "none"
			if hasattr(self, 'combo_density'):
				self.combo_density.blockSignals(True)
				self.combo_density.setCurrentIndex(0)
				self.combo_density.blockSignals(False)
			self.derivative_order = 0
			self.combo_derivative.setCurrentIndex(0)

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
				get_density_mode=lambda: self.density_mode,
				get_stats_hide_level=lambda: self.combo_stats_hide.currentIndex(),
				get_stats_shading_all=lambda: self.stats_shading_all,
				get_is_year_offset=lambda: self.is_year_offset,
				get_derivative_order=lambda: self.combo_derivative.currentIndex(),
				get_baseline_mode=lambda: self.baseline_mode,
				get_is_bar_chart=lambda: self.is_bar_chart
			)
			for combo in self.filter_widget_map.values():
				if isinstance(combo, QComboBox):
					combo.currentIndexChanged.connect(self._save_current_filters_to_memory)

			combo_moment = self.filter_widget_map.get('moment')
			if isinstance(combo_moment, QComboBox):
				combo_moment.currentIndexChanged.connect(self._update_view_year_dependencies)

			self.canvas.draw()
			self.setup_preset_buttons(title)
			self._restore_filters(title)
			self._update_bar_chart_visibility()
			self.redraw_current_plot()
		except Exception as e:
			self.ax.text(0.5, 0.5, f"Error:\n{e}", ha='center', va='center')

		self.canvas.draw()

	def set_redraw_fn(self, fn):
		self.current_redraw_fn = fn

	def redraw_current_plot(self):
		if callable(self.current_redraw_fn):
			self.current_redraw_fn()
		self.apply_plot_settings()

	def clear_tooltip_handler(self):
		self.cursor_hover_handler = None

	def update_stats_summary_panel(self, global_stats, year_stats=None):
		# Render stats in sidebar for both stats and non-stats modes
		if not global_stats:
			self.stats_panel.clear()
			return
		self.stats_panel.setPlainText(
			format_stats_panel_text(global_stats, year_stats, is_year_offset=self.is_year_offset)
		)

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


	def manual_refresh(self):
		"""Forces an immediate read of all log files and re-renders the current chart."""
		self.reload_log(is_interactive=True)

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