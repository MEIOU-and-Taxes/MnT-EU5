import glob
import json
import os
import re
from datetime import datetime
from functools import partial

import matplotlib.pyplot as plt
import pandas as pd
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence, QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QComboBox, QSlider, QLabel, QTextEdit, QMessageBox,
    QFileDialog, QProgressDialog, QApplication
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

from src.analysis_toolkit import AnalysisToolkitDialog
from src.constants import (
    REFRESH_PERIOD_MS, AUTOSAVE_PERIOD_MS, TARGET_FILE_NAME_ROOT,
    AUTOSAVE_FILE, ICON_PATH, GRAPH_INTRODUCTION, ERROR_FILE_NOT_FOUND
)
from src.parsing import log_parser
from src.plotting import chart_library, configs
from src.plotting.tooltip import InteractiveLineTooltip
from src.services.exporter import run_export_pipeline
from src.services.session_manager import save_session, load_session
from src.ui.stats_panel import format_stats_panel_text
from src.widgets.dialogs import ChartSelectionDialog

from tools.shared import fetch_logs
from tools.shared.fetch_logs import get_from_config

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MEIOU and Taxes Plotter")
        self.is_stats_mode = True
        self.current_redraw_fn = None

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
        self.is_log_scale = False
        self.is_moving_average = False
        self.period_value = 5
        self.chart_filter_memory = {}
        self.last_log_state = None

        self._build_ui()
        self.setup_shortcuts()
        self.load_key_configs()
        self.load_graph_definitions()
        self.display_info_screen()

        # Watchers
        self.timer_auto_reload = QTimer(self)
        self.timer_auto_reload.setInterval(REFRESH_PERIOD_MS)
        self.timer_auto_reload.timeout.connect(self.check_log_updates)
        self.timer_auto_reload.start()

        self.timer_auto_save = QTimer(self)
        self.timer_auto_save.setInterval(AUTOSAVE_PERIOD_MS)
        self.timer_auto_save.timeout.connect(self.auto_save_data)
        self.timer_auto_save.start()

    def _build_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.fig, self.ax = plt.subplots()
        self.plot_container = QHBoxLayout()
        self.canvas = FigureCanvas(self.fig)
        self.plot_container.addWidget(self.canvas, stretch=4)

        self.stats_panel = QTextEdit()
        self.stats_panel.setReadOnly(True)
        self.stats_panel.setFixedWidth(320)
        self.stats_panel.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e; color: #e0e0e0;
                border: 1px solid #3c3c3c; border-radius: 4px;
                font-family: Consolas, 'Courier New', monospace; font-size: 12px;
                padding: 8px; line-height: 1.4;
            }
        """)
        self.plot_container.addWidget(self.stats_panel, stretch=1)
        self.layout.addLayout(self.plot_container, 1)

        self.toolbar = NavigationToolbar(self.canvas, self)
        self.layout.addWidget(self.toolbar)

        # Controls
        self.top_button_layout = QHBoxLayout()
        self.btn_change_log_folder = QPushButton("Open log folder [Ctrl+L]")
        self.btn_charts = QPushButton("Charts [`]")
        self.combo_refresh = QComboBox()
        self.combo_refresh.addItems(["Refresh: 10s", "Refresh: 30s", "Refresh: 60s", "Refresh: 300s", "Refresh: 600s", "Refresh: Off"])

        self.btn_load_session = QPushButton("Load session [Ctrl+O]")
        self.btn_save_session = QPushButton("Save session [Ctrl+S]")
        self.combo_autosave = QComboBox()
        self.combo_autosave.addItems(["Auto-save: 1m", "Auto-save: 5m", "Auto-save: 10m", "No auto-save"])

        self.btn_clear_data = QPushButton("Clear data")
        self.btn_export_all = QPushButton("Export data [Ctrl+E]")
        self.btn_backup = QPushButton("Backup logs [Shift+S]")
        self.btn_analysis = QPushButton("Data analysis toolkit [A]")
        self.btn_fullscreen = QPushButton("Fullscreen [F]")
        self.btn_log_scale = QPushButton("Log scale [L]")
        self.btn_moving_avg = QPushButton("Moving avg [W]")

        self.slider_period = QSlider(Qt.Orientation.Horizontal)
        self.slider_period.setRange(2, 50)
        self.slider_period.setValue(self.period_value)
        self.slider_period.setFixedWidth(100)
        self.lbl_period_value = QLabel(f"Period: {self.period_value}")
        self.slider_period.setVisible(False)
        self.lbl_period_value.setVisible(False)

        self.combo_stats_bands = QComboBox()
        self.combo_stats_bands.addItems(["5 Bands (Quartiles)", "7 Bands (+ 5th/95th)", "9 Bands (+ 1st/99th)"])
        self.combo_stats_bands.setCurrentIndex(2)

        self.btn_stats_mode = QPushButton("Stats mode [T]")
        self.btn_stats_mode.setCheckable(True)
        self.btn_stats_mode.setChecked(True)
        self.btn_fullscreen.setCheckable(True)
        self.btn_log_scale.setCheckable(True)
        self.btn_moving_avg.setCheckable(True)

        for w in [self.btn_change_log_folder, self.btn_charts, self.combo_refresh, self.btn_load_session,
                  self.btn_save_session, self.combo_autosave, self.btn_clear_data, self.btn_export_all, self.btn_backup,
                  self.btn_analysis, self.btn_fullscreen, self.btn_log_scale, self.btn_moving_avg,
                  self.slider_period, self.lbl_period_value, self.btn_stats_mode, self.combo_stats_bands]:
            self.top_button_layout.addWidget(w)

        self.top_button_layout.addStretch(1)
        self.layout.addLayout(self.top_button_layout)

        self.preset_button_layout = QHBoxLayout()
        self.layout.addLayout(self.preset_button_layout)

        self.filter_layout = QGridLayout()
        self.layout.addLayout(self.filter_layout)

        # Wire UI Events
        self.combo_refresh.currentIndexChanged.connect(self._on_refresh_rate_changed)
        self.combo_autosave.currentIndexChanged.connect(self._on_autosave_rate_changed)
        self.btn_backup.clicked.connect(self.backup_log)
        self.btn_charts.clicked.connect(self.show_chart_list)
        self.btn_export_all.clicked.connect(lambda: run_export_pipeline(self.data, self.log_folder, self))
        self.btn_fullscreen.toggled.connect(lambda c: self.showFullScreen() if c else self.showNormal())
        self.btn_log_scale.toggled.connect(self.toggle_log_scale)
        self.btn_moving_avg.toggled.connect(self.toggle_moving_average)
        self.slider_period.valueChanged.connect(self._on_period_change)
        self.btn_analysis.clicked.connect(self.open_analysis_toolkit)
        self.btn_change_log_folder.clicked.connect(self.change_log_folder)
        self.btn_stats_mode.toggled.connect(self.toggle_stats_mode)
        self.combo_stats_bands.currentIndexChanged.connect(self.redraw_current_plot)
        self.btn_save_session.clicked.connect(self.manual_save)
        self.btn_load_session.clicked.connect(self.manual_load)
        self.btn_clear_data.clicked.connect(self.clear_data)

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Shift+S"), self, self.backup_log)
        QShortcut(QKeySequence("Ctrl+L"), self, self.change_log_folder)
        QShortcut(QKeySequence("A"), self, self.open_analysis_toolkit)
        QShortcut(QKeySequence("`"), self, self.show_chart_list)
        QShortcut(QKeySequence("F"), self, self.btn_fullscreen.toggle)
        QShortcut(QKeySequence("Ctrl+E"), self, lambda: run_export_pipeline(self.data, self.log_folder, self))
        QShortcut(QKeySequence("L"), self, self.btn_log_scale.toggle)
        QShortcut(QKeySequence("W"), self, self.btn_moving_avg.toggle)
        QShortcut(QKeySequence("T"), self, self.btn_stats_mode.toggle)
        QShortcut(QKeySequence("Ctrl+O"), self, self.manual_load)
        QShortcut(QKeySequence("Ctrl+S"), self, self.manual_save)

    def load_graph_definitions(self):
        registered = {
            'Building Types by Region': {'func': chart_library.graph_building_types, 'config': configs.BT_CONFIG},
            'Goods Prices by Region': {'func': chart_library.graph_goods_prices, 'config': configs.GP_CONFIG},
            'Market Statistics': {'func': chart_library.graph_markets, 'config': configs.MK_CONFIG},
            'Population by Region': {'func': chart_library.graph_population, 'config': configs.POP_CONFIG},
            'Road Coverage by Region': {'func': chart_library.graph_road_types, 'config': configs.RT_CONFIG},
            'Country Metrics': {'func': chart_library.graph_country_metrics, 'config': configs.CM_CONFIG},
        }
        self.graphs = registered
        self.chart_shortcuts.clear()
        for idx, chart_name in enumerate(sorted(self.graphs.keys())):
            hotkey = str(idx + 1)
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

    def display_chart(self, graph_info, title):
        self._save_current_filters_to_memory()

        self.current_graph_info = {'info': graph_info, 'title': title}
        self.is_log_scale = False
        self.btn_log_scale.setChecked(False)
        self.is_moving_average = False
        self.btn_moving_avg.setChecked(False)

        self._reset_filter_layout()
        self.ax.clear()
        self.fig.suptitle(title)
        self.fig.subplots_adjust(bottom=0.1, left=0.05, right=0.95, top=0.90)

        try:
            graph_info['func'](
                self.data, self.ax, self.filter_layout, self.filter_widgets,
                self.on_plot_updated, self.clear_tooltip_handler, self.filter_widget_map,
                lambda: self.is_moving_average, lambda: self.period_value,
                lambda: self.is_stats_mode, self.update_stats_summary_panel,
                self.get_stats_bands_count, set_redraw_fn=self.set_redraw_fn
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

    def clear_data(self):
        reply = QMessageBox.question(
            self, "Clear Data",
            "Are you sure you want to clear all loaded log data and reset caches?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.data = ""
            self.logs = []
            self.last_log_state = None
            self.chart_filter_memory.clear()
            log_parser.reset_cumulative_history()
            self.stats_panel.clear()
            self.display_info_screen("All data cleared. Click 'Open log folder' or refresh to reload.")


    def _restore_filters(self, title):
        for widget in self.filter_widget_map.values():
            widget.blockSignals(True)
        try:
            if title in self.chart_filter_memory:
                for k, val in self.chart_filter_memory[title].items():
                    if k in self.filter_widget_map:
                        idx = self.filter_widget_map[k].findText(val)
                        if idx != -1: self.filter_widget_map[k].setCurrentIndex(idx)
            elif title in self.key_configs and "F1" in self.key_configs[title]:
                for k, val in self.key_configs[title]["F1"].get("filters", {}).items():
                    if k in self.filter_widget_map:
                        idx = self.filter_widget_map[k].findText(val)
                        if idx != -1: self.filter_widget_map[k].setCurrentIndex(idx)
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
        if self.current_graph_info['title'] in ("Market Statistics", "Country Metrics"):
            return

        cat_k = self.current_graph_info['info']['config']['category_key']
        c_combo = self.filter_widget_map.get(cat_k)
        r_combo = self.filter_widget_map.get('region')
        if not c_combo or not r_combo:
            return

        for combo in (c_combo, r_combo):
            combo.blockSignals(True)
        try:
            if c_combo.currentIndex() != 0 and r_combo.currentIndex() == 0:
                idx = r_combo.findText(line_label)
                if idx != -1:
                    r_combo.setCurrentIndex(idx)
                    c_combo.setCurrentIndex(0)
            elif r_combo.currentIndex() != 0 and c_combo.currentIndex() == 0:
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
        self.stats_panel.setPlainText(format_stats_panel_text(global_stats, year_stats))

    def toggle_stats_mode(self, checked):
        self.is_stats_mode = checked
        self.stats_panel.setVisible(checked)
        self.combo_stats_bands.setVisible(checked)
        self.redraw_current_plot()

    def get_stats_bands_count(self):
        return [5, 7, 9][self.combo_stats_bands.currentIndex()]

    def toggle_log_scale(self, checked):
        self.is_log_scale = checked
        self.apply_plot_settings()

    def toggle_moving_average(self, checked):
        self.is_moving_average = checked
        self.slider_period.setVisible(checked)
        self.lbl_period_value.setVisible(checked)
        self.redraw_current_plot()

    def _on_period_change(self, val):
        self.period_value = val
        self.lbl_period_value.setText(f"Period: {val}")
        if self.is_moving_average:
            self.redraw_current_plot()

    def apply_plot_settings(self):
        if not (self.ax.get_lines() or self.ax.patches):
            return
        try:
            if self.is_log_scale:
                self.ax.set_yscale('log')
                b, _ = self.ax.get_ylim()
                if b <= 0: self.ax.set_ylim(bottom=0.1)
            else:
                self.ax.set_yscale('linear')
            self.canvas.draw_idle()
        except Exception:
            self.is_log_scale = False
            self.btn_log_scale.setChecked(False)
            self.ax.set_yscale('linear')
            self.canvas.draw_idle()

    def show_chart_list(self):
        dlg = ChartSelectionDialog(self.graphs, self.chart_hotkeys, self)
        if dlg.exec() and dlg.selected_chart:
            self.display_chart(self.graphs[dlg.selected_chart], dlg.selected_chart)

    def load_key_configs(self):
        if os.path.exists("key_configs.json"):
            try:
                with open("key_configs.json", "r") as f:
                    self.key_configs = json.load(f)
            except Exception as e:
                QMessageBox.critical(self, "Config Error", f"Error in key_configs.json: {e}")

    def setup_preset_buttons(self, chart_title):
        self.clear_preset_buttons()
        cfgs = self.key_configs.get(chart_title, {})
        for key in sorted(cfgs.keys(), key=lambda x: int(x[1:]) if x[1:].isdigit() else 0):
            cfg = cfgs[key]
            btn = QPushButton(f"{cfg.get('description', '')} [{key}]")
            btn.clicked.connect(partial(self._apply_preset_filter, cfg.get("filters", {})))
            self.preset_button_layout.addWidget(btn)
            self.preset_buttons.append(btn)

            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(partial(self._apply_preset_filter, cfg.get("filters", {})))
            self.preset_shortcuts.append(sc)
        self.preset_button_layout.addStretch(1)

    def _apply_preset_filter(self, filters):
        for combo in self.filter_widget_map.values():
            combo.blockSignals(True)
        try:
            for k, v in filters.items():
                if k in self.filter_widget_map:
                    idx = self.filter_widget_map[k].findText(v)
                    if idx != -1: self.filter_widget_map[k].setCurrentIndex(idx)
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

    def reload_log(self, is_interactive=True):
        saved_info = self.current_graph_info
        log_parser.clear_all_caches()
        self.logs, self.data = self.read_all_logs()

        if is_interactive and not self.logs:
            if QMessageBox.warning(self, "No Logs", f"No logs in {self.log_folder}.\nChange?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.change_log_folder()
                return

        if saved_info:
            self.display_chart(saved_info['info'], saved_info['title'])
        else:
            self.display_info_screen()

    def check_log_updates(self):
        files = self.get_all_log_files()
        if not files: return
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
            self.reload_log(is_interactive=False)

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

    def load_initial_data(self):
        if os.path.exists(AUTOSAVE_FILE):
            mod_time = datetime.fromtimestamp(os.path.getmtime(AUTOSAVE_FILE)).strftime("%Y-%m-%d %H:%M")
            reply = QMessageBox.question(self, "Restore Session?",
                                         f"Saved session from {mod_time} found.\nRestore?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes and self.load_session_file(AUTOSAVE_FILE):
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
        cur = session.get("current_chart")
        if cur and cur in self.graphs:
            self.display_chart(self.graphs[cur], cur)
        else:
            self.display_info_screen("Session loaded.")
        return True

    def auto_save_data(self):
        if self.combo_autosave.currentIndex() != 3 and self.data:
            self._save_current_filters_to_memory()
            title = self.current_graph_info['title'] if self.current_graph_info else None
            save_session(AUTOSAVE_FILE, self.data, self.logs, self.chart_filter_memory, title)

    def _on_refresh_rate_changed(self, idx):
        intervals = [10, 30, 60, 300, 600, 0]
        ms = intervals[idx] * 1000
        if ms == 0: self.timer_auto_reload.stop()
        else:
            self.timer_auto_reload.setInterval(ms)
            self.timer_auto_reload.start()

    def _on_autosave_rate_changed(self, idx):
        intervals = [60, 300, 600, 0]
        ms = intervals[idx] * 1000
        if ms == 0: self.timer_auto_save.stop()
        else:
            self.timer_auto_save.setInterval(ms)
            self.timer_auto_save.start()

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
        if not self.data or self.combo_autosave.currentIndex() == 3:
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