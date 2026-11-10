import matplotlib.pyplot as plt
from PyQt6.QtGui import QShortcut, QKeySequence
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit, QComboBox, QGridLayout

from src.constants import POS_SUBPLOT_TOP_EDGE, POS_SUBPLOT_BOTTOM_EDGE, POS_SUBPLOT_LEFT_EDGE, POS_SUBPLOT_RIGHT_EDGE, \
	POS_SUBPLOT_HSPACE, POS_SUBPLOT_WSPACE, STATS_PANEL_WIDTH
from src.widgets.custom_combobox import RightClickableComboBox


class ToolbarBuilder:
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
		self.stats_panel.setVisible(self.is_stats_panel_visible)
		self.plot_container.addWidget(self.stats_panel, stretch=1)
		self.layout.addLayout(self.plot_container, 1)

		self.toolbar = NavigationToolbar(self.canvas, self)
		self.layout.addWidget(self.toolbar)

		# Controls layout
		self.top_button_layout = QHBoxLayout()

		# History back and forward buttons
		self.btn_history_back = QPushButton("◀")
		self.btn_history_back.setToolTip("Back in history [Alt+Left]")
		self.btn_history_back.setFixedWidth(30)
		self.btn_history_back.setEnabled(False)
		self.btn_history_back.clicked.connect(self.history_back)

		self.btn_history_forward = QPushButton("▶")
		self.btn_history_forward.setToolTip("Forward in history [Alt+Right]")
		self.btn_history_forward.setFixedWidth(30)
		self.btn_history_forward.setEnabled(False)
		self.btn_history_forward.clicked.connect(self.history_forward)

		self.btn_charts = QPushButton("Charts [`]")
		self.btn_preset_config = QPushButton("Presets [Ctrl+P]")
		self.btn_alerts = QPushButton("Alerts [Shift+A]")
		self.btn_alerts.setToolTip("Configure automated alerts and trigger thresholds")
		self.btn_alerts.clicked.connect(self.open_alert_dialog)

		self.btn_refresh = QPushButton("Refresh [Ctrl+R]")
		self.btn_refresh.setToolTip("Reload log files from disk and re-render immediately")

		self.btn_bar_chart = QPushButton("[B]ar chart")
		self.btn_bar_chart.setCheckable(True)
		self.btn_bar_chart.setChecked(self.is_bar_chart)
		self.btn_bar_chart.setToolTip("Toggle Bar chart mode (single year view)")
		self.btn_bar_chart.toggled.connect(self.act_bar_chart.setChecked)

		self.btn_find = QPushButton("Find [Ctrl+F]")
		self.btn_find.setToolTip("Quick search all dropdown values in the current chart")
		self.btn_find.clicked.connect(self.open_filter_search)

		self.btn_stats_mode = QPushButton("Stats mode [T]")
		self.btn_stats_mode.setCheckable(True)
		self.btn_stats_mode.setChecked(self.is_stats_mode)

		self.btn_year_offset = QPushButton("Relative [Y]ear")
		self.btn_year_offset.setCheckable(True)
		self.btn_year_offset.setChecked(self.is_year_offset)
		self.btn_year_offset.setToolTip("Toggle time axis between absolute and relative")

		self.btn_stats_panel = QPushButton("[S]tats panel")
		self.btn_stats_panel.setCheckable(True)
		self.btn_stats_panel.setChecked(self.is_stats_panel_visible)
		self.btn_stats_panel.setToolTip("Toggle sidebar statistics panel")
		self.btn_stats_panel.toggled.connect(self.act_stats_panel.setChecked)

		self.lbl_percentiles_to_hide = QLabel("Percentiles to hide:")
		self.combo_stats_hide = QComboBox()
		self.combo_stats_hide.addItems([
			"None",
			"Min / Max",
			"Min/Max, 99th/1st",
			"Min/Max, 99th/1st, 95th/5th"
		])
		if 0 <= self.stats_hide_idx < self.combo_stats_hide.count():
			self.combo_stats_hide.setCurrentIndex(self.stats_hide_idx)
		self.lbl_percentiles_to_hide.setVisible(self.is_stats_mode)
		self.combo_stats_hide.setVisible(self.is_stats_mode)
		self.combo_stats_hide.setToolTip("Select outliers/percentile bands to hide from the chart.")
		self.combo_stats_hide.currentIndexChanged.connect(self._on_stats_hide_changed)

		# Density Dropdown with label & right-click support
		self.lbl_density = QLabel("Density:")
		self.combo_density = RightClickableComboBox()
		self.combo_density.addItems(["Base", "Population", "Location"])
		density_idx_map = {"none": 0, "population": 1, "location": 2}
		self.combo_density.setCurrentIndex(density_idx_map.get(self.density_mode, 0))
		self.combo_density.setToolTip("Select density normalization (Right-click to reset): Base, Population [P], Location [G]")
		self.combo_density.currentIndexChanged.connect(self._on_density_changed)

		# Baseline Mode Dropdown (Ratio / Difference)
		self.lbl_baseline = QLabel("Baseline:")
		self.combo_baseline = RightClickableComboBox()
		self.combo_baseline.addItems(["Base", "Ratio (%)", "Difference (Δ)"])
		base_idx_map = {"none": 0, "ratio": 1, "difference": 2}
		self.combo_baseline.setCurrentIndex(base_idx_map.get(getattr(self, 'baseline_mode', 'none'), 0))
		self.combo_baseline.setToolTip("Scale values from start year: Base, Ratio (%) [Shift+I], Difference (Δ) [I]")
		self.combo_baseline.currentIndexChanged.connect(self._on_baseline_changed)

		# Derivative Dropdown
		self.lbl_derivative = QLabel("Rate of change:")
		self.combo_derivative = RightClickableComboBox()
		self.combo_derivative.addItems(["Base", "Rate (Δ)", "Rel Rate (%Δ)", "Acceleration (Δ²)"])
		self.combo_derivative.setCurrentIndex(self.derivative_order)
		self.combo_derivative.setToolTip("Select derivative order (Right-click to reset): Base, Rate (Δ) [R], Rel Rate (%Δ) [R], Acceleration (Δ²) [Shift+R]")
		self.combo_derivative.currentIndexChanged.connect(self._on_derivative_changed)

		self.btn_log_scale = QPushButton("[L]og scale")
		self.btn_log_scale.setCheckable(True)
		self.btn_log_scale.setChecked(self.is_log_scale)

		self.btn_moving_avg = QPushButton("Smooth [W]")
		self.btn_moving_avg.setCheckable(True)
		self.btn_moving_avg.setChecked(self.is_moving_average)
		self.btn_moving_avg.setVisible(True)

		for w in [self.btn_history_back, self.btn_history_forward,
				  self.btn_charts, self.btn_preset_config, self.btn_alerts, self.btn_find, self.btn_refresh,
				  self.btn_bar_chart, self.btn_year_offset, self.btn_stats_mode,
				  self.lbl_density, self.combo_density,
				  self.lbl_baseline, self.combo_baseline,
				  self.lbl_derivative, self.combo_derivative,
				  self.btn_log_scale, self.btn_moving_avg,
				  self.lbl_percentiles_to_hide, self.combo_stats_hide]:
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

	def setup_shortcuts(self):
		# Keyboard shortcuts are already handled by QAction shortcuts in the menu bar.

		# Hotkeys to step metric/category backward and forward
		self.sc_prev_metric = QShortcut(QKeySequence(","), self)
		self.sc_prev_metric.activated.connect(self.select_previous_metric)

		self.sc_next_metric = QShortcut(QKeySequence("."), self)
		self.sc_next_metric.activated.connect(self.select_next_metric)

		# Preset page shortcuts shifted to Shift+Left / Shift+Right to prevent conflicts with Alt+Left/Right history
		self.sc_prev_preset_page = QShortcut(QKeySequence("Shift+Left"), self)
		self.sc_prev_preset_page.activated.connect(self._prev_preset_page)

		self.sc_next_preset_page = QShortcut(QKeySequence("Shift+Right"), self)
		self.sc_next_preset_page.activated.connect(self._next_preset_page)
