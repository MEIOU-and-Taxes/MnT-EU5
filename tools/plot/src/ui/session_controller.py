import glob
import os
from datetime import datetime

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from src.constants import AUTOSAVE_FILE, AUTOSAVE_DIR, AUTOSAVES_KEPT
from src.services.session_manager import save_session, load_session


class SessionController:
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