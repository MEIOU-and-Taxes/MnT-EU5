import glob
import os
from datetime import datetime

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QInputDialog

from src.constants import AUTOSAVE_FILE, AUTOSAVE_DIR, AUTOSAVES_KEPT
from src.services.session_manager import save_session, load_session


class SessionController:
	def prompt_new_session_name(self, default_name="session"):
		"""Prompts the user to optionally name a new plot session."""
		name, ok = QInputDialog.getText(
			self,
			"New Plot Session",
			"Enter a name for this plot/session:\n(Used for autosaves and default save filename)",
			text=getattr(self, 'session_name', default_name)
		)
		if ok and name.strip():
			self.session_name = name.strip()
		else:
			self.session_name = default_name
		return self.session_name

	def manual_save(self):
		s_name = getattr(self, 'session_name', 'session')
		default_filename = f"{s_name}.dat"
		path, _ = QFileDialog.getSaveFileName(self, "Save Session", default_filename, "Session Data (*.dat)")
		if path:
			self._save_current_filters_to_memory()
			title = self.current_graph_info['title'] if self.current_graph_info else None
			self.session_name = os.path.splitext(os.path.basename(path))[0]
			ok = save_session(path, self.data, self.logs, self.chart_filter_memory, title, session_name=self.session_name)
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

		loaded_name = session.get("session_name")
		if not loaded_name:
			base = os.path.splitext(os.path.basename(filepath))[0]
			for prefix in ["autosave_", "session_backup"]:
				if base.startswith(prefix):
					base = base[len(prefix):]
			loaded_name = base.strip("_") or "session"
		self.session_name = loaded_name

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
			s_name = getattr(self, 'session_name', 'session')

			named_autosave = os.path.join(AUTOSAVE_DIR, f"autosave_{s_name}.dat")
			save_session(named_autosave, self.data, self.logs, self.chart_filter_memory, title, session_name=s_name)

			timestamp_file = os.path.join(AUTOSAVE_DIR, f"autosave_{s_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dat")
			save_session(timestamp_file, self.data, self.logs, self.chart_filter_memory, title, session_name=s_name)

			all_autosaves = sorted(glob.glob(os.path.join(AUTOSAVE_DIR, f"autosave_{s_name}_*.dat")), key=os.path.getmtime)
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
		self.session_name = "session"
		recent_save = self.find_most_recent_autosave()
		if recent_save:
			mod_time = datetime.fromtimestamp(os.path.getmtime(recent_save)).strftime("%Y-%m-%d %H:%M")
			file_label = os.path.basename(recent_save)
			msg_box = QMessageBox(self)
			msg_box.setWindowTitle("Restore Session?")
			msg_box.setText(f"Most recent saved session found:\n{file_label} ({mod_time})\n\nRestore?")
			btn_yes = msg_box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
			btn_no = msg_box.addButton("No, start new", QMessageBox.ButtonRole.NoRole)
			btn_no_clear = msg_box.addButton("No, and clear error logs", QMessageBox.ButtonRole.DestructiveRole)
			msg_box.setDefaultButton(btn_yes)
			msg_box.exec()
			clicked = msg_box.clickedButton()

			if clicked == btn_yes:
				if self.load_session_file(recent_save):
					return
			elif clicked == btn_no_clear:
				self.clear_log_files_on_disk()
				self.prompt_new_session_name()
				self.reload_log(is_interactive=True)
				return
			else:
				self.prompt_new_session_name()
				self.reload_log(is_interactive=True)
				return

		self.prompt_new_session_name()
		self.reload_log(is_interactive=True)