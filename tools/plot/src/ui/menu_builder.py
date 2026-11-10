from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QKeySequence, QDesktopServices

from src.services.exporter import run_export_pipeline

class MenuBuilder:
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
		act_presets.setShortcut(QKeySequence("Ctrl+P"))
		act_presets.triggered.connect(self.open_preset_config)
		menu_charts.addAction(act_presets)

		# View Menu
		menu_view = menubar.addMenu("&View")

		self.act_history_back = QAction("Back in History", self)
		self.act_history_back.setShortcut(QKeySequence("Alt+Left"))
		self.act_history_back.triggered.connect(self.history_back)
		self.act_history_back.setEnabled(False)
		menu_view.addAction(self.act_history_back)
		self.addAction(self.act_history_back)

		self.act_history_forward = QAction("Forward in History", self)
		self.act_history_forward.setShortcut(QKeySequence("Alt+Right"))
		self.act_history_forward.triggered.connect(self.history_forward)
		self.act_history_forward.setEnabled(False)
		menu_view.addAction(self.act_history_forward)
		self.addAction(self.act_history_forward)

		menu_view.addSeparator()

		act_find = QAction("Find Filter / Metric...", self)
		act_find.setShortcut(QKeySequence("Ctrl+F"))
		act_find.triggered.connect(self.open_filter_search)
		menu_view.addAction(act_find)
		self.addAction(act_find)

		self.act_fullscreen = QAction("Fullscreen", self, checkable=True)
		self.act_fullscreen.setShortcut(QKeySequence("F"))
		self.act_fullscreen.toggled.connect(self.toggle_fullscreen)
		menu_view.addAction(self.act_fullscreen)

		self.act_stats_panel = QAction("Stats panel", self, checkable=True)
		self.act_stats_panel.setChecked(self.is_stats_panel_visible)
		self.act_stats_panel.setShortcut(QKeySequence("S"))
		self.act_stats_panel.toggled.connect(self.toggle_stats_panel)
		menu_view.addAction(self.act_stats_panel)
		self.addAction(self.act_stats_panel)

		self.act_bar_chart = QAction("Bar chart", self, checkable=True)
		self.act_bar_chart.setChecked(self.is_bar_chart)
		self.act_bar_chart.setShortcut(QKeySequence("B"))
		self.act_bar_chart.toggled.connect(self.toggle_bar_chart)
		menu_view.addAction(self.act_bar_chart)
		self.addAction(self.act_bar_chart)

		self.act_year_offset = QAction("Relative year", self, checkable=True)
		self.act_year_offset.setChecked(self.is_year_offset)
		self.act_year_offset.setShortcut(QKeySequence("Y"))
		self.act_year_offset.toggled.connect(self.toggle_year_offset)
		menu_view.addAction(self.act_year_offset)

		self.act_stats_mode = QAction("Stats mode", self, checkable=True)
		self.act_stats_mode.setChecked(self.is_stats_mode)
		self.act_stats_mode.setShortcut(QKeySequence("T"))
		self.act_stats_mode.toggled.connect(self.toggle_stats_mode)
		menu_view.addAction(self.act_stats_mode)

		self.act_baseline_ratio = QAction("Baseline: Ratio (%)", self)
		self.act_baseline_ratio.setShortcut(QKeySequence("Shift+I"))
		self.act_baseline_ratio.triggered.connect(self.handle_i_shortcut)
		menu_view.addAction(self.act_baseline_ratio)
		self.addAction(self.act_baseline_ratio)

		self.act_baseline_diff = QAction("Baseline: Difference (Δ)", self)
		self.act_baseline_diff.setShortcut(QKeySequence("I"))
		self.act_baseline_diff.triggered.connect(self.handle_shift_i_shortcut)
		menu_view.addAction(self.act_baseline_diff)
		self.addAction(self.act_baseline_diff)

		self.act_density_loc = QAction("Density: Loc", self, checkable=True)
		self.act_density_loc.setChecked(self.density_mode == "location")
		self.act_density_loc.setShortcut(QKeySequence("G"))
		self.act_density_loc.triggered.connect(self.toggle_location_density)
		menu_view.addAction(self.act_density_loc)

		self.act_density_pop = QAction("Density: Pop", self, checkable=True)
		self.act_density_pop.setChecked(self.density_mode == "population")
		self.act_density_pop.setShortcut(QKeySequence("P"))
		self.act_density_pop.triggered.connect(self.toggle_population_density)
		menu_view.addAction(self.act_density_pop)

		self.act_rate_toggle = QAction("Derivative: Rate (R)", self)
		self.act_rate_toggle.setShortcut(QKeySequence("R"))
		self.act_rate_toggle.triggered.connect(self.handle_r_shortcut)
		menu_view.addAction(self.act_rate_toggle)
		self.addAction(self.act_rate_toggle)

		self.act_accel_toggle = QAction("Derivative: Acceleration (Shift+R)", self)
		self.act_accel_toggle.setShortcut(QKeySequence("Shift+R"))
		self.act_accel_toggle.triggered.connect(self.handle_shift_r_shortcut)
		menu_view.addAction(self.act_accel_toggle)
		self.addAction(self.act_accel_toggle)

		self.act_log_scale = QAction("Symlog scale", self, checkable=True)
		self.act_log_scale.setChecked(self.is_log_scale)
		self.act_log_scale.setShortcut(QKeySequence("L"))
		self.act_log_scale.toggled.connect(self.toggle_log_scale)
		menu_view.addAction(self.act_log_scale)

		self.act_moving_avg = QAction("Smooth", self, checkable=True)
		self.act_moving_avg.setChecked(self.is_moving_average)
		self.act_moving_avg.setShortcut(QKeySequence("W"))
		self.act_moving_avg.toggled.connect(self.toggle_moving_average)
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

		act_alerts = QAction("Manage Alerts...", self)
		act_alerts.setShortcut(QKeySequence("Shift+A"))
		act_alerts.triggered.connect(self.open_alert_dialog)
		menu_tools.addAction(act_alerts)
		self.addAction(act_alerts)

		act_refresh = QAction("Refresh Logs", self)
		act_refresh.setShortcut(QKeySequence("Ctrl+R"))
		act_refresh.triggered.connect(self.manual_refresh)
		menu_tools.addAction(act_refresh)

		act_computed_series = QAction("Computed Series", self)
		act_computed_series.setShortcut(QKeySequence("C"))
		act_computed_series.triggered.connect(self.open_computed_series_dialog)
		menu_tools.addAction(act_computed_series)

		act_analysis = QAction("Data Analysis Toolkit", self)
		act_analysis.setShortcut(QKeySequence("A"))
		act_analysis.triggered.connect(self.open_analysis_toolkit)
		menu_tools.addAction(act_analysis)

		menu_tools.addSeparator()

		act_settings = QAction("Settings...", self)
		act_settings.setShortcut(QKeySequence("Ctrl+,"))
		act_settings.triggered.connect(self.open_settings_dialog)
		menu_tools.addAction(act_settings)

		# Help Menu
		menu_help = menubar.addMenu("&Help")

		act_docs = QAction("Documentation", self)
		act_docs.triggered.connect(
			lambda: QDesktopServices.openUrl(QUrl("https://github.com/MEIOU-and-Taxes/MnT-EU5/wiki#plotter")))
		menu_help.addAction(act_docs)
		self.addAction(act_docs)

		for act in [act_open_folder, act_backup, act_load_sess, act_save_sess,
					act_clear_data, act_export, act_charts, act_presets,
					self.act_fullscreen, self.act_stats_mode, self.act_year_offset,
					self.act_density_loc, self.act_density_pop, self.act_log_scale,
					self.act_moving_avg, act_refresh, act_computed_series, act_analysis, act_settings]:
			self.addAction(act)

		act_toggle_alerts = QAction("Enable Alerts Monitoring", self, checkable=True)
		act_toggle_alerts.setChecked(self.alerts_enabled)
		act_toggle_alerts.setShortcut(QKeySequence("Alt+A"))
		act_toggle_alerts.toggled.connect(self._set_alerts_enabled)
		menu_tools.addAction(act_toggle_alerts)
		self.addAction(act_toggle_alerts)

		act_toggle_sounds = QAction("Enable Alert Sounds", self, checkable=True)
		act_toggle_sounds.setChecked(self.alert_sounds_enabled)
		act_toggle_sounds.setShortcut(QKeySequence("Alt+S"))
		act_toggle_sounds.toggled.connect(self._set_alert_sounds_enabled)
		menu_tools.addAction(act_toggle_sounds)
		self.addAction(act_toggle_sounds)