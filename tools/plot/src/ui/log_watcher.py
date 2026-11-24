import glob
import os
import re

from PyQt6.QtWidgets import QMessageBox, QFileDialog

import src.parsing.stores
from src.constants import TARGET_FILE_NAME_ROOT
from src.parsing import log_parser
from tools.shared import fetch_logs


class MainMenuLogWatcher:
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
			src.parsing.stores.reset_cumulative_history()

		modified_any = False
		for fn in files:
			if force_all or src.parsing.stores.should_parse_file(fn):
				log_parser.parse_log_file(fn)
				modified_any = True

		if modified_any:
			src.parsing.stores.clear_all_caches()
			self.data = "loaded"

		self.logs = files

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


	def _update_last_log_state(self):
		cur = []
		for f in self.get_all_log_files():
			try:
				s = os.stat(f)
				cur.append((f, s.st_size, s.st_mtime))
			except OSError:
				pass
		self.last_log_state = cur

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
				src.parsing.stores.reset_cumulative_history()
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
		src.parsing.stores.reset_cumulative_history()
		self.stats_panel.clear()

		# If requested, clear the contents of error.log and the 5 rotated files (error.1.log to error.5.log)
		cleared_files_count = 0
		if clicked == btn_clear_both:
			cleared_files_count = self.clear_log_files_on_disk()

		self._update_last_log_state()

		if hasattr(self, 'prompt_new_session_name'):
			self.prompt_new_session_name()

		status_msg = (
			f"App data cleared and contents of {cleared_files_count} log file(s) emptied."
			if clicked == btn_clear_both
			else "App data cleared."
		)
		self.display_info_screen(f"{status_msg}\nPlay more or refresh to reload.")

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

	def change_log_folder(self):
		new_path = QFileDialog.getExistingDirectory(self, "Select Log Folder", self.log_folder)
		if new_path and new_path != self.log_folder:
			self.log_folder = new_path
			fetch_logs.update_config_file('Paths', 'log_directory', new_path)
			self.reload_log()
