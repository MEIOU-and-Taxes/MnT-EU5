# Thanks to the Seelowe/Justice Fighter, the author of the code this is based on

import configparser
import glob
import os
import sys
import traceback
from functools import partial

import matplotlib.pyplot as plt
import numpy as np
from PIL.PSDraw import ERROR_PS
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import (QApplication, QDialog, QGridLayout, QHBoxLayout,
							 QHeaderView, QMainWindow, QPushButton,
							 QTableWidget, QTableWidgetItem, QVBoxLayout,
							 QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

import chart_library as all_graphs
from interactive_tooltip import InteractiveLineTooltip
from tools.shared.fetch_logs import get_log_directory_from_config

TARGET_FILE_NAME_ROOT = 'debug'
ERROR_FILE_NOT_FOUND = 'debug.log not found. Please include in the config the correct path to the logs folder'
is_path_found = True

graph_introduction = """
Welcome to the M&T graphing tool!

Press '/' to see the list of available graphs.
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
		self.setWindowTitle("MEIOU and Taxes - Sim graphs")
		self.setGeometry(100, 100, 1800, 800)

		# --- Data and State ---
		self.log_folder = get_log_directory_from_config()
		self.logs = []
		self.data = ""
		self.graphs = {}
		self.chart_hotkeys = {}
		self.chart_shortcuts = []
		self.cursor_hover_handler = None
		self.filter_widgets = []

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
		button_layout = QHBoxLayout()
		self.btn_refresh = QPushButton("Refresh data [F5]")
		self.btn_backup = QPushButton("Backup logs [Ctrl+S]")
		self.btn_charts = QPushButton("Charts [`]")
		button_layout.addWidget(self.btn_refresh)
		button_layout.addWidget(self.btn_backup)
		button_layout.addWidget(self.btn_charts)
		button_layout.addStretch(1) # Pushes buttons to the left
		self.layout.addLayout(button_layout)

		# --- Bottom Filter Widgets Layout ---
		self.filter_layout = QGridLayout()
		self.layout.addLayout(self.filter_layout)

		# --- Connect Signals ---
		self.btn_refresh.clicked.connect(self.reload_log)
		self.btn_backup.clicked.connect(self.backup_log)
		self.btn_charts.clicked.connect(self.show_chart_list)

		# --- Initialize ---
		self.setup_shortcuts()
		self.load_graph_definitions()
		self.reload_log()

	def setup_shortcuts(self):
		"""Setup global keyboard shortcuts."""
		QShortcut(QKeySequence("F5"), self, self.reload_log)
		QShortcut(QKeySequence("Ctrl+S"), self, self.backup_log)
		QShortcut(QKeySequence("`"), self, self.show_chart_list)
		QShortcut(QKeySequence("F11"), self, self.toggle_fullscreen)

	def toggle_fullscreen(self):
		"""Toggles the main window between fullscreen and normal modes."""
		if self.isFullScreen():
			self.showNormal()
		else:
			self.showFullScreen()

	def load_graph_definitions(self):
		"""Load graph functions from the all_graphs module."""
		all_graphs.get_data = self.get_data
		self.graphs = {
			getattr(all_graphs, name).__name__[5:].replace("_", " "): (
				getattr(all_graphs, name).__doc__,
				getattr(all_graphs, name)
			)
			for name in dir(all_graphs)
			if callable(getattr(all_graphs, name)) and name.lower().startswith("graph")
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
			title, graph_func = self.graphs[chart_name]
			self.display_chart(graph_func, title)

	def display_info_screen(self, msg=None):
		"""Displays the initial welcome message on the plot."""
		self.cursor_hover_handler = None
		self.clear_filter_widgets()
		self.ax.clear()
		self.ax.set_title("Menu")
		text_to_show = ERROR_FILE_NOT_FOUND if not is_path_found else msg if msg else graph_introduction.strip()
		self.ax.text(0.5, 0.5, text_to_show,
					 horizontalalignment="center", verticalalignment="center")
		self.canvas.draw()

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

	def setup_tooltip_handler(self):
		"""Creates a new tooltip handler for the current axes."""
		self.cursor_hover_handler = InteractiveLineTooltip(self.ax)
		self.cursor_hover_handler.setup_tooltip_handler()

	def clear_tooltip_handler(self):
		"""Clears any existing tooltip handler."""
		self.cursor_hover_handler = None

	def display_chart(self, graph_func, title):
		"""Clears the axes and plots a new graph."""
		self.clear_filter_widgets()
		self.ax.clear()
		self.fig.subplots_adjust(bottom=0.1, left=0.05, right=0.95, top=0.925) # Reset adjustments

		try:
			graph_func(
				self.data,
				self.ax,
				self.filter_layout,
				self.filter_widgets,
				self.setup_tooltip_handler,
				self.clear_tooltip_handler
			)
			self.ax.set_title(title)
			self.canvas.draw() # Draw the canvas first, to update the graph elements

		except Exception as e:
			self.ax.text(0.5, 0.5, f"Error:\n{e}", ha='center', va='center')
			traceback.print_exc()

		self.ax.set_title(title)
		self.canvas.draw()

	def backup_log(self):
		"""Backs up the current game.log."""
		if not self.logs:
			print("No log files found to determine the next backup number.")
			return
		last_log_num = int(os.path.basename(self.logs[-1])[5:-4])
		try:
			os.rename("game.log", f"game_{last_log_num + 1}.log")
			print(f"Backed up game.log to game_{last_log_num + 1}.log")
		except FileNotFoundError:
			print("game.log not found, nothing to back up.")
		except Exception as e:
			print(f"Error backing up log: {e}")
		self.display_info_screen()

	def reload_log(self):
		"""Reads all log files from the configured directory."""
		self.logs, self.data = read_all_logs(self.log_folder)
		self.display_info_screen()

	def show_chart_list(self):
		"""Opens the chart selection dialog."""
		dialog = ChartSelectionDialog(self.graphs, self)
		if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_chart:
			chart_name = dialog.selected_chart
			title, graph_func = self.graphs[chart_name]
			self.display_chart(graph_func, title)


def read_all_logs(log_directory):
	"""Read file(s) from a specified directory."""
	content_list = []
	search_pattern = os.path.join(log_directory, TARGET_FILE_NAME_ROOT + "_*.log")
	files = glob.glob(search_pattern)
	if files:
		files.sort(key=lambda x: int(os.path.basename(x)[5:-4]))

	for fn in files:
		with open(fn, "r", encoding="utf-8") as f:
			content_list.append(f.read())
			is_path_found = True

	game_log_path = os.path.join(log_directory, f"{TARGET_FILE_NAME_ROOT}.log")
	try:
		with open(game_log_path, "r", encoding="utf-8") as f:
			content_list.append(f.read())
			is_path_found = True
	except FileNotFoundError:
		print(f"WARNING: Could not find {game_log_path}")
		is_path_found = False

	print(f'Read {len(files) + (1 if os.path.exists(game_log_path) else 0)} log file(s) from "{log_directory}"')
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