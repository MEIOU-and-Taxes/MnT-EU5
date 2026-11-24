from PyQt6.QtWidgets import QComboBox, QMessageBox, QGridLayout

from src.widgets.filter_dialog import FilterSearchDialog
from src.widgets.hotkey_utils import sort_hotkeys

class FilterController:
	def _restore_filters(self, title):
			for widget in self.filter_widget_map.values():
				widget.blockSignals(True)
			try:
				if title in self.chart_filter_memory:
					for k, val in self.chart_filter_memory[title].items():
						target_key = k
						if target_key not in self.filter_widget_map:
							if target_key == 'region' and 'country' in self.filter_widget_map:
								target_key = 'country'
							elif target_key == 'region' and 'market' in self.filter_widget_map:
								target_key = 'market'
							elif target_key == 'metric' and 'credit_metric' in self.filter_widget_map:
								target_key = 'credit_metric'
						if target_key in self.filter_widget_map:
							idx = self.filter_widget_map[target_key].findText(val)
							if idx != -1: self.filter_widget_map[target_key].setCurrentIndex(idx)
				elif title in self.key_configs and self.key_configs[title]:
					sorted_keys = sort_hotkeys(self.key_configs[title].keys())
					first_preset = self.key_configs[title][sorted_keys[0]]
					for k, val in first_preset.get("filters", {}).items():
						target_key = k
						if target_key not in self.filter_widget_map:
							if target_key == 'region' and 'country' in self.filter_widget_map:
								target_key = 'country'
							elif target_key == 'region' and 'market' in self.filter_widget_map:
								target_key = 'market'
							elif target_key == 'metric' and 'credit_metric' in self.filter_widget_map:
								target_key = 'credit_metric'
						if target_key in self.filter_widget_map:
							idx = self.filter_widget_map[target_key].findText(val)
							if idx != -1: self.filter_widget_map[target_key].setCurrentIndex(idx)
			finally:
				for widget in self.filter_widget_map.values():
					widget.blockSignals(False)

	def _save_current_filters_to_memory(self):
		if self.current_graph_info:
			title = self.current_graph_info['title']
			self.chart_filter_memory[title] = {
				k: w.currentText() for k, w in self.filter_widget_map.items() if isinstance(w, QComboBox)
			}


	def _get_metric_combobox(self):
		"""Returns the primary metric/category combobox for the current chart."""
		if not self.current_graph_info:
			return None
		cat_key = self.current_graph_info['info']['config'].get('category_key')
		combo = self.filter_widget_map.get(cat_key)
		if isinstance(combo, QComboBox):
			return combo
		# Fallback to any metric-like key
		for key in ['country_metric', 'credit_metric', 'statistic', 'good', 'building', 'road_type']:
			w = self.filter_widget_map.get(key)
			if isinstance(w, QComboBox):
				return w
		return None

	def select_previous_metric(self):
		combo = self._get_metric_combobox()
		if combo and combo.count() > 0:
			new_idx = (combo.currentIndex() - 1) % combo.count()
			combo.setCurrentIndex(new_idx)

	def select_next_metric(self):
		combo = self._get_metric_combobox()
		if combo and combo.count() > 0:
			new_idx = (combo.currentIndex() + 1) % combo.count()
			combo.setCurrentIndex(new_idx)

	def open_filter_search(self):
		"""Opens Ctrl+F search dialog to quickly find and select dropdown options."""
		if not self.current_graph_info or not self.filter_widget_map:
			QMessageBox.information(self, "No Chart", "Please open a chart first to search its filters.")
			return

		dlg = FilterSearchDialog(self.filter_widget_map, self)
		if dlg.exec() and dlg.selected_target:
			combo, target_val = dlg.selected_target
			idx = self._find_matching_combo_index(combo, target_val)
			if idx != -1:
				combo.setCurrentIndex(idx)
				self.redraw_current_plot()

	def handle_line_click(self, line_label):
		if not self.current_graph_info or self.is_stats_mode:
			return

		cat_k = self.current_graph_info['info']['config']['category_key']
		entity_k = self.current_graph_info['info']['config'].get('entity_key', 'region')
		c_combo = self.filter_widget_map.get(cat_k)
		r_combo = self.filter_widget_map.get(entity_k)
		if not c_combo or not r_combo:
			return

		for combo in (c_combo, r_combo):
			combo.blockSignals(True)
		try:
			all_cat = self.current_graph_info['info']['config'].get('all_category_str')
			if (c_combo.currentIndex() != 0 or all_cat is None) and r_combo.currentIndex() == 0:
				idx = self._find_matching_combo_index(r_combo, line_label)
				if idx != -1:
					r_combo.setCurrentIndex(idx)
					if all_cat:
						c_combo.setCurrentIndex(0)
			elif r_combo.currentIndex() != 0 and (c_combo.currentIndex() == 0 and all_cat):
				idx = self._find_matching_combo_index(c_combo, line_label)
				if idx != -1:
					c_combo.setCurrentIndex(idx)
					r_combo.setCurrentIndex(0)
		finally:
			for combo in (c_combo, r_combo):
				combo.blockSignals(False)
		self.redraw_current_plot()

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
