from PyQt6.QtWidgets import QComboBox


class HistoryManager:
	"""Manages undo/redo-style navigation history of charts, filters, and display modes."""

	def init_history(self):
		self.history_stack = []
		self.history_index = -1
		self._navigating_history = False

	def record_history_state(self):
		if getattr(self, '_navigating_history', False):
			return
		if not getattr(self, 'current_graph_info', None):
			return

		current_state = {
			'chart_title': self.current_graph_info['title'],
			'filters': {
				k: w.currentText()
				for k, w in self.filter_widget_map.items()
				if isinstance(w, QComboBox)
			},
			'is_bar_chart': getattr(self, 'is_bar_chart', False),
			'is_stats_mode': getattr(self, 'is_stats_mode', True),
			'density_mode': getattr(self, 'density_mode', 'none'),
			'derivative_order': getattr(self, 'derivative_order', 0),
			'baseline_mode': getattr(self, 'baseline_mode', 'none'),
			'is_year_offset': getattr(self, 'is_year_offset', False),
			'is_log_scale': getattr(self, 'is_log_scale', False),
			'is_moving_average': getattr(self, 'is_moving_average', False),
			'stats_hide_idx': self.combo_stats_hide.currentIndex() if hasattr(self, 'combo_stats_hide') else 0,
		}

		if 0 <= self.history_index < len(self.history_stack):
			if self.history_stack[self.history_index] == current_state:
				return

		self.history_stack = self.history_stack[:self.history_index + 1]
		self.history_stack.append(current_state)

		if len(self.history_stack) > 100:
			self.history_stack.pop(0)

		self.history_index = len(self.history_stack) - 1
		self._update_history_ui()

	def history_back(self):
		if self.history_index > 0:
			self.history_index -= 1
			self._apply_history_state(self.history_stack[self.history_index])

	def history_forward(self):
		if self.history_index < len(self.history_stack) - 1:
			self.history_index += 1
			self._apply_history_state(self.history_stack[self.history_index])

	def _apply_history_state(self, state):
		self._navigating_history = True
		try:
			target_chart = state.get('chart_title')
			if not self.current_graph_info or self.current_graph_info['title'] != target_chart:
				if target_chart in self.graphs:
					self.display_chart(self.graphs[target_chart], target_chart, preserve_toggles=True)

			d_mode = state.get('density_mode', 'none')
			if self.density_mode != d_mode:
				self.set_density_mode(d_mode)

			b_mode = state.get('baseline_mode', 'none')
			if self.baseline_mode != b_mode:
				self.set_baseline_mode(b_mode)

			d_order = state.get('derivative_order', 0)
			if getattr(self, 'derivative_order', 0) != d_order:
				if hasattr(self, 'combo_derivative'):
					self.combo_derivative.setCurrentIndex(d_order)

			bar_chart = state.get('is_bar_chart', False)
			if getattr(self, 'is_bar_chart', False) != bar_chart:
				self.toggle_bar_chart(bar_chart)

			yr_off = state.get('is_year_offset', False)
			if getattr(self, 'is_year_offset', False) != yr_off:
				self.toggle_year_offset(yr_off)

			st_mode = state.get('is_stats_mode', True)
			if getattr(self, 'is_stats_mode', True) != st_mode:
				self.toggle_stats_mode(st_mode)

			lg_scale = state.get('is_log_scale', False)
			if getattr(self, 'is_log_scale', False) != lg_scale:
				self.toggle_log_scale(lg_scale)

			mv_avg = state.get('is_moving_average', False)
			if getattr(self, 'is_moving_average', False) != mv_avg:
				self.toggle_moving_average(mv_avg)

			sh_idx = state.get('stats_hide_idx', 0)
			if hasattr(self, 'combo_stats_hide') and self.combo_stats_hide.currentIndex() != sh_idx:
				self.combo_stats_hide.setCurrentIndex(sh_idx)

			saved_filters = state.get('filters', {})
			for k, v in saved_filters.items():
				combo = self.filter_widget_map.get(k)
				if isinstance(combo, QComboBox):
					combo.blockSignals(True)
					idx = self._find_matching_combo_index(combo, v)
					if idx != -1:
						combo.setCurrentIndex(idx)
					combo.blockSignals(False)

			self.redraw_current_plot()
		finally:
			self._navigating_history = False
			self._update_history_ui()

	def _update_history_ui(self):
		can_back = self.history_index > 0
		can_forward = self.history_index < len(self.history_stack) - 1

		if hasattr(self, 'act_history_back'):
			self.act_history_back.setEnabled(can_back)
		if hasattr(self, 'act_history_forward'):
			self.act_history_forward.setEnabled(can_forward)
		if hasattr(self, 'btn_history_back'):
			self.btn_history_back.setEnabled(can_back)
		if hasattr(self, 'btn_history_forward'):
			self.btn_history_forward.setEnabled(can_forward)