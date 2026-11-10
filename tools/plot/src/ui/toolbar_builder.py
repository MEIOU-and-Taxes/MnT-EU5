"""Toolbar and central chart container builder."""
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit, QComboBox, QGridLayout

from src.constants import (
	POS_SUBPLOT_TOP_EDGE, POS_SUBPLOT_BOTTOM_EDGE, POS_SUBPLOT_LEFT_EDGE, POS_SUBPLOT_RIGHT_EDGE,
	POS_SUBPLOT_HSPACE, POS_SUBPLOT_WSPACE, STATS_PANEL_WIDTH
)
from src.widgets.custom_combobox import RightClickableComboBox


def build_toolbar_ui(window):
	window.central_widget = QWidget()
	window.setCentralWidget(window.central_widget)
	window.layout = QVBoxLayout(window.central_widget)

	window.fig, window.ax = plt.subplots()
	window.fig.subplots_adjust(
		top=POS_SUBPLOT_TOP_EDGE,
		bottom=POS_SUBPLOT_BOTTOM_EDGE,
		left=POS_SUBPLOT_LEFT_EDGE,
		right=POS_SUBPLOT_RIGHT_EDGE,
		hspace=POS_SUBPLOT_HSPACE,
		wspace=POS_SUBPLOT_WSPACE
	)

	window.plot_container = QHBoxLayout()
	window.canvas = FigureCanvas(window.fig)
	window.plot_container.addWidget(window.canvas, stretch=4)

	window.stats_panel = QTextEdit()
	window.stats_panel.setReadOnly(True)
	window.stats_panel.setFixedWidth(STATS_PANEL_WIDTH)
	window.stats_panel.setStyleSheet("""
		QTextEdit {
			background-color: #1e1e1e; color: #e0e0e0;
			border: 1px solid #3c3c3c; border-radius: 4px;
			font-family: Consolas, 'Courier New', monospace; font-size: 12px;
			padding: 8px; line-height: 1.4;
		}
	""")
	window.stats_panel.setVisible(window.is_stats_panel_visible)
	window.plot_container.addWidget(window.stats_panel, stretch=1)
	window.layout.addLayout(window.plot_container, 1)

	window.toolbar = NavigationToolbar(window.canvas, window)
	window.layout.addWidget(window.toolbar)

	# Controls layout
	window.top_button_layout = QHBoxLayout()

	# History back and forward buttons
	window.btn_history_back = QPushButton("◀")
	window.btn_history_back.setToolTip("Back in history [Alt+Left]")
	window.btn_history_back.setFixedWidth(30)
	window.btn_history_back.setEnabled(False)
	window.btn_history_back.clicked.connect(window.history_back)

	window.btn_history_forward = QPushButton("▶")
	window.btn_history_forward.setToolTip("Forward in history [Alt+Right]")
	window.btn_history_forward.setFixedWidth(30)
	window.btn_history_forward.setEnabled(False)
	window.btn_history_forward.clicked.connect(window.history_forward)

	window.btn_charts = QPushButton("Charts [`]")
	window.btn_preset_config = QPushButton("Presets [Ctrl+P]")
	window.btn_alerts = QPushButton("Alerts [Shift+A]")
	window.btn_alerts.setToolTip("Configure automated alerts and trigger thresholds")
	window.btn_alerts.clicked.connect(window.open_alert_dialog)

	window.btn_refresh = QPushButton("Refresh [Ctrl+R]")
	window.btn_refresh.setToolTip("Reload log files from disk and re-render immediately")

	window.btn_bar_chart = QPushButton("[B]ar chart")
	window.btn_bar_chart.setCheckable(True)
	window.btn_bar_chart.setChecked(window.is_bar_chart)
	window.btn_bar_chart.setToolTip("Toggle Bar chart mode (single year view)")
	window.btn_bar_chart.toggled.connect(window.act_bar_chart.setChecked)

	window.btn_find = QPushButton("Find [Ctrl+F]")
	window.btn_find.setToolTip("Quick search all dropdown values in the current chart")
	window.btn_find.clicked.connect(window.open_filter_search)

	window.btn_stats_mode = QPushButton("Stats mode [T]")
	window.btn_stats_mode.setCheckable(True)
	window.btn_stats_mode.setChecked(window.is_stats_mode)

	window.btn_year_offset = QPushButton("Relative [Y]ear")
	window.btn_year_offset.setCheckable(True)
	window.btn_year_offset.setChecked(window.is_year_offset)
	window.btn_year_offset.setToolTip("Toggle time axis between absolute and relative")

	window.btn_stats_panel = QPushButton("[S]tats panel")
	window.btn_stats_panel.setCheckable(True)
	window.btn_stats_panel.setChecked(window.is_stats_panel_visible)
	window.btn_stats_panel.setToolTip("Toggle sidebar statistics panel")
	window.btn_stats_panel.toggled.connect(window.act_stats_panel.setChecked)

	window.lbl_percentiles_to_hide = QLabel("Percentiles to hide:")
	window.combo_stats_hide = QComboBox()
	window.combo_stats_hide.addItems([
		"None",
		"Min / Max",
		"Min/Max, 99th/1st",
		"Min/Max, 99th/1st, 95th/5th"
	])
	if 0 <= window.stats_hide_idx < window.combo_stats_hide.count():
		window.combo_stats_hide.setCurrentIndex(window.stats_hide_idx)
	window.lbl_percentiles_to_hide.setVisible(window.is_stats_mode)
	window.combo_stats_hide.setVisible(window.is_stats_mode)
	window.combo_stats_hide.setToolTip("Select outliers/percentile bands to hide from the chart.")
	window.combo_stats_hide.currentIndexChanged.connect(window._on_stats_hide_changed)

	# Density Dropdown with label & right-click support
	window.lbl_density = QLabel("Density:")
	window.combo_density = RightClickableComboBox()
	window.combo_density.addItems(["Base", "Population", "Location"])
	density_idx_map = {"none": 0, "population": 1, "location": 2}
	window.combo_density.setCurrentIndex(density_idx_map.get(window.density_mode, 0))
	window.combo_density.setToolTip("Select density normalization (Right-click to reset): Base, Population [P], Location [G]")
	window.combo_density.currentIndexChanged.connect(window._on_density_changed)

	# Baseline Mode Dropdown (Ratio / Difference)
	window.lbl_baseline = QLabel("Baseline:")
	window.combo_baseline = RightClickableComboBox()
	window.combo_baseline.addItems(["Base", "Ratio (%)", "Difference (Δ)"])
	base_idx_map = {"none": 0, "ratio": 1, "difference": 2}
	window.combo_baseline.setCurrentIndex(base_idx_map.get(getattr(window, 'baseline_mode', 'none'), 0))
	window.combo_baseline.setToolTip("Scale values from start year: Base, Ratio (%) [Shift+I], Difference (Δ) [I]")
	window.combo_baseline.currentIndexChanged.connect(window._on_baseline_changed)

	# Derivative Dropdown
	window.lbl_derivative = QLabel("Rate of change:")
	window.combo_derivative = RightClickableComboBox()
	window.combo_derivative.addItems(["Base", "Rate (Δ)", "Rel Rate (%Δ)", "Acceleration (Δ²)"])
	window.combo_derivative.setCurrentIndex(window.derivative_order)
	window.combo_derivative.setToolTip("Select derivative order (Right-click to reset): Base, Rate (Δ) [R], Rel Rate (%Δ) [R], Acceleration (Δ²) [Shift+R]")
	window.combo_derivative.currentIndexChanged.connect(window._on_derivative_changed)

	window.btn_log_scale = QPushButton("[L]og scale")
	window.btn_log_scale.setCheckable(True)
	window.btn_log_scale.setChecked(window.is_log_scale)

	window.btn_moving_avg = QPushButton("Smooth [W]")
	window.btn_moving_avg.setCheckable(True)
	window.btn_moving_avg.setChecked(window.is_moving_average)
	window.btn_moving_avg.setVisible(True)

	for w in [
		window.btn_history_back, window.btn_history_forward,
		window.btn_charts, window.btn_preset_config, window.btn_alerts, window.btn_find, window.btn_refresh,
		window.btn_bar_chart, window.btn_year_offset, window.btn_stats_mode,
		window.lbl_density, window.combo_density,
		window.lbl_baseline, window.combo_baseline,
		window.lbl_derivative, window.combo_derivative,
		window.btn_log_scale, window.btn_moving_avg,
		window.lbl_percentiles_to_hide, window.combo_stats_hide
	]:
		window.top_button_layout.addWidget(w)

	window.top_button_layout.addStretch(1)
	window.layout.addLayout(window.top_button_layout)

	window.preset_button_layout = QHBoxLayout()
	window.layout.addLayout(window.preset_button_layout)

	window.filter_layout = QGridLayout()
	window.layout.addLayout(window.filter_layout)

	# Wire UI Events
	window.btn_refresh.clicked.connect(window.manual_refresh)
	window.btn_preset_config.clicked.connect(window.open_preset_config)
	window.btn_charts.clicked.connect(window.show_chart_list)
	window.btn_log_scale.toggled.connect(window.act_log_scale.setChecked)
	window.btn_moving_avg.toggled.connect(window.act_moving_avg.setChecked)
	window.btn_stats_mode.toggled.connect(window.act_stats_mode.setChecked)
	window.btn_year_offset.toggled.connect(window.act_year_offset.setChecked)