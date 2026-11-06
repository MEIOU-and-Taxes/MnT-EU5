import os
from functools import partial

from PyQt6.QtWidgets import QPushButton, QLabel, QComboBox

from src.constants import PRESETS_PER_PAGE
from src.widgets.hotkey_utils import sort_hotkeys


class PresetBar:
	def _render_preset_buttons(self):
		# Clear existing layout widgets without clearing global QShortcuts
		while self.preset_button_layout.count():
			item = self.preset_button_layout.takeAt(0)
			if item.widget():
				item.widget().deleteLater()
		self.preset_buttons.clear()

		if not getattr(self, 'current_preset_chart', None):
			return

		cfgs = self.key_configs.get(self.current_preset_chart, {})
		sorted_keys = sort_hotkeys(cfgs.keys())
		total_presets = len(sorted_keys)

		if total_presets == 0:
			return

		total_pages = max(1, (total_presets + PRESETS_PER_PAGE - 1) // PRESETS_PER_PAGE)
		if self.preset_page >= total_pages:
			self.preset_page = total_pages - 1
		elif self.preset_page < 0:
			self.preset_page = 0

		start_idx = self.preset_page * PRESETS_PER_PAGE
		end_idx = min(start_idx + PRESETS_PER_PAGE, total_presets)
		page_keys = sorted_keys[start_idx:end_idx]

		for key in page_keys:
			cfg = cfgs[key]
			btn = QPushButton(f"{cfg.get('description', '')} [{key}]")
			btn.clicked.connect(partial(self._apply_preset_filter, cfg.get("filters", {})))
			self.preset_button_layout.addWidget(btn)
			self.preset_buttons.append(btn)

		self.preset_button_layout.addStretch(1)

		if total_pages > 1:
			btn_prev = QPushButton("◀")
			btn_prev.setToolTip("Previous preset page [Shift+Left]")
			btn_prev.setFixedWidth(32)
			btn_prev.clicked.connect(self._prev_preset_page)

			lbl_page = QLabel(f"Page {self.preset_page + 1}/{total_pages}")
			lbl_page.setStyleSheet("font-weight: bold; padding: 0 4px;")

			btn_next = QPushButton("▶")
			btn_next.setToolTip("Next preset page [Shift+Right]")
			btn_next.setFixedWidth(32)
			btn_next.clicked.connect(self._next_preset_page)

			self.preset_button_layout.addWidget(btn_prev)
			self.preset_button_layout.addWidget(lbl_page)
			self.preset_button_layout.addWidget(btn_next)


	def _prev_preset_page(self):
		if not getattr(self, 'current_preset_chart', None):
			return
		cfgs = self.key_configs.get(self.current_preset_chart, {})
		total_pages = max(1, (len(cfgs) + PRESETS_PER_PAGE - 1) // PRESETS_PER_PAGE)
		if total_pages <= 1:
			return
		self.preset_page = (self.preset_page - 1) % total_pages
		self._render_preset_buttons()


	def _next_preset_page(self):
		if not getattr(self, 'current_preset_chart', None):
			return
		cfgs = self.key_configs.get(self.current_preset_chart, {})
		total_pages = max(1, (len(cfgs) + PRESETS_PER_PAGE - 1) // PRESETS_PER_PAGE)
		if total_pages <= 1:
			return
		self.preset_page = (self.preset_page + 1) % total_pages
		self._render_preset_buttons()

	def clear_preset_buttons(self):
		while self.preset_button_layout.count():
			item = self.preset_button_layout.takeAt(0)
			if item.widget():
				item.widget().deleteLater()
		self.preset_buttons.clear()
		for sc in self.preset_shortcuts:
			sc.deleteLater()
		self.preset_shortcuts.clear()


	def _apply_preset_filter(self, filters):
		for combo in self.filter_widget_map.values():
			combo.blockSignals(True)
		try:
			for k, v in filters.items():
				target_key = k
				if target_key not in self.filter_widget_map:
					if target_key in ('good', 'building', 'road_type', 'statistic') and 'regional_metric' in self.filter_widget_map:
						target_key = 'regional_metric'
					elif target_key == 'credit_metric' and 'country_metric' in self.filter_widget_map:
						target_key = 'country_metric'
					elif target_key == 'region' and 'country' in self.filter_widget_map:
						target_key = 'country'
					elif target_key == 'region' and 'market' in self.filter_widget_map:
						target_key = 'market'
				if target_key in self.filter_widget_map:
					idx = self._find_matching_combo_index(self.filter_widget_map[target_key], v)
					if idx != -1: self.filter_widget_map[target_key].setCurrentIndex(idx)
		finally:
			for combo in self.filter_widget_map.values():
				combo.blockSignals(False)
		self.redraw_current_plot()

	def check_log_updates(self):
		"""Runs every 5 seconds to inspect files on disk and ingest changes."""
		files = self.get_all_log_files()
		if not files:
			return
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
			self.read_and_parse_logs()
			self.has_new_data = True

	def _find_matching_combo_index(self, widget: QComboBox, val: str) -> int:
		"""Finds item index, gracefully resolving with or without ' price' suffix."""
		idx = widget.findText(val)
		if idx != -1:
			return idx
		if not val.lower().endswith(" price"):
			idx = widget.findText(f"{val} price")
			if idx != -1:
				return idx
		if val.lower().endswith(" price"):
			idx = widget.findText(val[:-6].strip())
			if idx != -1:
				return idx
		return -1
