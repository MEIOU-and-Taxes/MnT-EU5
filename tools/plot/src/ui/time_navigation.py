from PyQt6.QtCore import Qt


class TimeNavigation:
	def _get_available_moments(self):
		combo = self.filter_widget_map.get('from_year') or self.filter_widget_map.get('moment')
		if not combo or combo.count() <= 1:
			return []
		moments = []
		for i in range(1, combo.count()):
			m = combo.itemData(i)
			if m is not None:
				moments.append(m)
		return sorted(moments)


	def adjust_year_start(self, delta):
		# If in bar chart mode, adjust View Year instead
		if self.is_bar_chart:
			self.adjust_moment(delta)
			return

		combo = self.filter_widget_map.get('from_year')
		if not combo or combo.count() <= 1:
			return
		moments = self._get_available_moments()
		if not moments:
			return

		min_year, max_year = moments[0], moments[-1]
		cur_year = combo.currentData()
		if cur_year is None:
			cur_year = min_year

		target_year = cur_year + delta

		to_combo = self.filter_widget_map.get('to_year')
		end_year = to_combo.currentData() if to_combo else None
		upper_limit = end_year if end_year is not None else max_year
		target_year = min(target_year, upper_limit)

		if target_year <= min_year:
			combo.setCurrentIndex(0)
		else:
			best_m = min(moments, key=lambda m: abs(m - target_year))
			if best_m > upper_limit:
				best_m = upper_limit
			idx = combo.findData(best_m)
			if idx != -1:
				combo.setCurrentIndex(idx)


	def adjust_year_end(self, delta):
		if self.is_bar_chart:
			self.adjust_moment(delta)
			return

		combo = self.filter_widget_map.get('to_year')
		if not combo or combo.count() <= 1:
			return
		moments = self._get_available_moments()
		if not moments:
			return

		min_year, max_year = moments[0], moments[-1]
		cur_year = combo.currentData()
		if cur_year is None:
			cur_year = max_year

		target_year = cur_year + delta

		from_combo = self.filter_widget_map.get('from_year')
		start_year = from_combo.currentData() if from_combo else None
		lower_limit = start_year if start_year is not None else min_year
		target_year = max(target_year, lower_limit)

		if target_year >= max_year:
			combo.setCurrentIndex(0)
		else:
			best_m = min(moments, key=lambda m: abs(m - target_year))
			if best_m < lower_limit:
				best_m = lower_limit
			idx = combo.findData(best_m)
			if idx != -1:
				combo.setCurrentIndex(idx)


	def adjust_moment(self, delta):
		combo = self.filter_widget_map.get('moment')
		if not combo or combo.count() <= 1:
			return
		moments = self._get_available_moments()
		if not moments:
			return

		cur_year = combo.currentData() or moments[-1]
		target_year = cur_year + delta
		best_m = min(moments, key=lambda m: abs(m - target_year))
		idx = combo.findData(best_m)
		if idx != -1:
			combo.setCurrentIndex(idx)


	def eventFilter(self, obj, event):
		if event.type() == event.Type.KeyPress:
			mods = event.modifiers()
			is_keypad = bool(mods & Qt.KeyboardModifier.KeypadModifier)
			if is_keypad:
				step = 100 if (mods & Qt.KeyboardModifier.ShiftModifier) else (
					10 if (mods & Qt.KeyboardModifier.ControlModifier) else 1)
				key = event.key()

				# Numpad 8: increment year start
				if key in (Qt.Key.Key_8, Qt.Key.Key_Up):
					self.adjust_year_start(step)
					return True
				# Numpad 2: decrement year start
				elif key in (Qt.Key.Key_2, Qt.Key.Key_Down):
					self.adjust_year_start(-step)
					return True
				# Numpad 6: increment year end
				elif key in (Qt.Key.Key_6, Qt.Key.Key_Right):
					self.adjust_year_end(step)
					return True
				# Numpad 4: decrement year end
				elif key in (Qt.Key.Key_4, Qt.Key.Key_Left):
					self.adjust_year_end(-step)
					return True

		return super().eventFilter(obj, event)