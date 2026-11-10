from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QKeySequence, QDesktopServices

from src.services.exporter import run_export_pipeline


def build_menu(window):
	menubar = window.menuBar()

	# --- File Menu ---
	menu_file = menubar.addMenu("&File")

	act_open_folder = QAction("Open Log Folder", window)
	act_open_folder.setShortcut(QKeySequence("Ctrl+L"))
	act_open_folder.triggered.connect(window.change_log_folder)
	menu_file.addAction(act_open_folder)

	act_backup = QAction("Backup Logs", window)
	act_backup.setShortcut(QKeySequence("Shift+S"))
	act_backup.triggered.connect(window.backup_log)
	menu_file.addAction(act_backup)

	menu_file.addSeparator()

	act_load_sess = QAction("Load Session...", window)
	act_load_sess.setShortcut(QKeySequence("Ctrl+O"))
	act_load_sess.triggered.connect(window.manual_load)
	menu_file.addAction(act_load_sess)

	act_save_sess = QAction("Save Session...", window)
	act_save_sess.setShortcut(QKeySequence("Ctrl+S"))
	act_save_sess.triggered.connect(window.manual_save)
	menu_file.addAction(act_save_sess)

	act_clear_data = QAction("Clear Data...", window)
	act_clear_data.triggered.connect(window.clear_data)
	menu_file.addAction(act_clear_data)

	menu_file.addSeparator()

	act_export = QAction("Export Data to CSV", window)
	act_export.setShortcut(QKeySequence("Ctrl+E"))
	act_export.triggered.connect(lambda: run_export_pipeline(window.data, window.log_folder, window))
	menu_file.addAction(act_export)

	act_appdata = QAction("Open AppData Folder", window)
	act_appdata.triggered.connect(window.open_appdata_folder)
	menu_file.addAction(act_appdata)

	menu_file.addSeparator()

	act_exit = QAction("Exit", window)
	act_exit.triggered.connect(window.close)
	menu_file.addAction(act_exit)

	# --- Charts Menu ---
	menu_charts = menubar.addMenu("&Charts")

	act_charts = QAction("Select Chart...", window)
	act_charts.setShortcut(QKeySequence("`"))
	act_charts.triggered.connect(window.show_chart_list)
	menu_charts.addAction(act_charts)

	act_presets = QAction("Configure Presets...", window)
	act_presets.setShortcut(QKeySequence("Ctrl+P"))
	act_presets.triggered.connect(window.open_preset_config)
	menu_charts.addAction(act_presets)

	# --- View Menu ---
	menu_view = menubar.addMenu("&View")

	window.act_history_back = QAction("Back in History", window)
	window.act_history_back.setShortcut(QKeySequence("Alt+Left"))
	window.act_history_back.triggered.connect(window.history_back)
	window.act_history_back.setEnabled(False)
	menu_view.addAction(window.act_history_back)
	window.addAction(window.act_history_back)

	window.act_history_forward = QAction("Forward in History", window)
	window.act_history_forward.setShortcut(QKeySequence("Alt+Right"))
	window.act_history_forward.triggered.connect(window.history_forward)
	window.act_history_forward.setEnabled(False)
	menu_view.addAction(window.act_history_forward)
	window.addAction(window.act_history_forward)

	menu_view.addSeparator()

	act_find = QAction("Find Filter / Metric...", window)
	act_find.setShortcut(QKeySequence("Ctrl+F"))
	act_find.triggered.connect(window.open_filter_search)
	menu_view.addAction(act_find)
	window.addAction(act_find)

	window.act_fullscreen = QAction("Fullscreen", window, checkable=True)
	window.act_fullscreen.setShortcut(QKeySequence("F"))
	window.act_fullscreen.toggled.connect(window.toggle_fullscreen)
	menu_view.addAction(window.act_fullscreen)

	window.act_stats_panel = QAction("Stats panel", window, checkable=True)
	window.act_stats_panel.setChecked(window.is_stats_panel_visible)
	window.act_stats_panel.setShortcut(QKeySequence("S"))
	window.act_stats_panel.toggled.connect(window.toggle_stats_panel)
	menu_view.addAction(window.act_stats_panel)
	window.addAction(window.act_stats_panel)

	window.act_bar_chart = QAction("Bar chart", window, checkable=True)
	window.act_bar_chart.setChecked(window.is_bar_chart)
	window.act_bar_chart.setShortcut(QKeySequence("B"))
	window.act_bar_chart.toggled.connect(window.toggle_bar_chart)
	menu_view.addAction(window.act_bar_chart)
	window.addAction(window.act_bar_chart)

	window.act_year_offset = QAction("Relative year", window, checkable=True)
	window.act_year_offset.setChecked(window.is_year_offset)
	window.act_year_offset.setShortcut(QKeySequence("Y"))
	window.act_year_offset.toggled.connect(window.toggle_year_offset)
	menu_view.addAction(window.act_year_offset)

	window.act_stats_mode = QAction("Stats mode", window, checkable=True)
	window.act_stats_mode.setChecked(window.is_stats_mode)
	window.act_stats_mode.setShortcut(QKeySequence("T"))
	window.act_stats_mode.toggled.connect(window.toggle_stats_mode)
	menu_view.addAction(window.act_stats_mode)

	window.act_baseline_ratio = QAction("Baseline: Ratio (%)", window)
	window.act_baseline_ratio.setShortcut(QKeySequence("Shift+I"))
	window.act_baseline_ratio.triggered.connect(window.handle_i_shortcut)
	menu_view.addAction(window.act_baseline_ratio)
	window.addAction(window.act_baseline_ratio)

	window.act_baseline_diff = QAction("Baseline: Difference (Δ)", window)
	window.act_baseline_diff.setShortcut(QKeySequence("I"))
	window.act_baseline_diff.triggered.connect(window.handle_shift_i_shortcut)
	menu_view.addAction(window.act_baseline_diff)
	window.addAction(window.act_baseline_diff)

	window.act_density_loc = QAction("Density: Loc", window, checkable=True)
	window.act_density_loc.setChecked(window.density_mode == "location")
	window.act_density_loc.setShortcut(QKeySequence("G"))
	window.act_density_loc.triggered.connect(window.toggle_location_density)
	menu_view.addAction(window.act_density_loc)

	window.act_density_pop = QAction("Density: Pop", window, checkable=True)
	window.act_density_pop.setChecked(window.density_mode == "population")
	window.act_density_pop.setShortcut(QKeySequence("P"))
	window.act_density_pop.triggered.connect(window.toggle_population_density)
	menu_view.addAction(window.act_density_pop)

	window.act_rate_toggle = QAction("Derivative: Rate (R)", window)
	window.act_rate_toggle.setShortcut(QKeySequence("R"))
	window.act_rate_toggle.triggered.connect(window.handle_r_shortcut)
	menu_view.addAction(window.act_rate_toggle)
	window.addAction(window.act_rate_toggle)

	window.act_accel_toggle = QAction("Derivative: Acceleration (Shift+R)", window)
	window.act_accel_toggle.setShortcut(QKeySequence("Shift+R"))
	window.act_accel_toggle.triggered.connect(window.handle_shift_r_shortcut)
	menu_view.addAction(window.act_accel_toggle)
	window.addAction(window.act_accel_toggle)

	window.act_log_scale = QAction("Symlog scale", window, checkable=True)
	window.act_log_scale.setChecked(window.is_log_scale)
	window.act_log_scale.setShortcut(QKeySequence("L"))
	window.act_log_scale.toggled.connect(window.toggle_log_scale)
	menu_view.addAction(window.act_log_scale)

	window.act_moving_avg = QAction("Smooth", window, checkable=True)
	window.act_moving_avg.setChecked(window.is_moving_average)
	window.act_moving_avg.setShortcut(QKeySequence("W"))
	window.act_moving_avg.toggled.connect(window.toggle_moving_average)
	menu_view.addAction(window.act_moving_avg)

	act_hide_inc = QAction("Hide more percentiles", window)
	act_hide_inc.setShortcut(QKeySequence("["))
	act_hide_inc.triggered.connect(window.increase_stats_hide)
	menu_view.addAction(act_hide_inc)
	window.addAction(act_hide_inc)

	act_hide_dec = QAction("Show more percentiles", window)
	act_hide_dec.setShortcut(QKeySequence("]"))
	act_hide_dec.triggered.connect(window.decrease_stats_hide)
	menu_view.addAction(act_hide_dec)
	window.addAction(act_hide_dec)

	window.act_stats_shading_all = QAction("Shade all percentile bands", window, checkable=True)
	window.act_stats_shading_all.setChecked(window.stats_shading_all)
	window.act_stats_shading_all.toggled.connect(window.toggle_stats_shading_all)
	menu_view.addAction(window.act_stats_shading_all)
	window.addAction(window.act_stats_shading_all)

	# --- Tools Menu ---
	menu_tools = menubar.addMenu("&Tools")

	act_alerts = QAction("Manage Alerts...", window)
	act_alerts.setShortcut(QKeySequence("Shift+A"))
	act_alerts.triggered.connect(window.open_alert_dialog)
	menu_tools.addAction(act_alerts)
	window.addAction(act_alerts)

	act_refresh = QAction("Refresh Logs", window)
	act_refresh.setShortcut(QKeySequence("Ctrl+R"))
	act_refresh.triggered.connect(window.manual_refresh)
	menu_tools.addAction(act_refresh)

	act_computed_series = QAction("Computed Series", window)
	act_computed_series.setShortcut(QKeySequence("C"))
	act_computed_series.triggered.connect(window.open_computed_series_dialog)
	menu_tools.addAction(act_computed_series)

	act_analysis = QAction("Data Analysis Toolkit", window)
	act_analysis.setShortcut(QKeySequence("A"))
	act_analysis.triggered.connect(window.open_analysis_toolkit)
	menu_tools.addAction(act_analysis)

	menu_tools.addSeparator()

	act_settings = QAction("Settings...", window)
	act_settings.setShortcut(QKeySequence("Ctrl+,"))
	act_settings.triggered.connect(window.open_settings_dialog)
	menu_tools.addAction(act_settings)

	act_toggle_alerts = QAction("Enable Alerts Monitoring", window, checkable=True)
	act_toggle_alerts.setChecked(window.alerts_enabled)
	act_toggle_alerts.setShortcut(QKeySequence("Alt+A"))
	act_toggle_alerts.toggled.connect(window.set_alerts_enabled)
	menu_tools.addAction(act_toggle_alerts)
	window.addAction(act_toggle_alerts)

	act_toggle_sounds = QAction("Enable Alert Sounds", window, checkable=True)
	act_toggle_sounds.setChecked(window.alert_sounds_enabled)
	act_toggle_sounds.setShortcut(QKeySequence("Alt+S"))
	act_toggle_sounds.toggled.connect(window.set_alert_sounds_enabled)
	menu_tools.addAction(act_toggle_sounds)
	window.addAction(act_toggle_sounds)

	# --- Help Menu ---
	menu_help = menubar.addMenu("&Help")

	act_docs = QAction("Documentation", window)
	act_docs.triggered.connect(
		lambda: QDesktopServices.openUrl(QUrl("https://github.com/MEIOU-and-Taxes/MnT-EU5/wiki#plotter"))
	)
	menu_help.addAction(act_docs)
	window.addAction(act_docs)