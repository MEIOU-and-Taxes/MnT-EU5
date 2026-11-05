import numpy as np
from PyQt6.QtWidgets import QMessageBox

from src.constants import MINIMUM_NUMBER_FOR_LOG_PLOTS
from src.parsing import log_parser
from src.parsing.stores import tg_cumulative_store, mk_cumulative_store
from src.plotting.tooltip import InteractiveLineTooltip


class ViewNodes:
	def toggle_stats_panel(self, checked):
		self.is_stats_panel_visible = checked
		if self.btn_stats_panel.isChecked() != checked:
			self.btn_stats_panel.blockSignals(True)
			self.btn_stats_panel.setChecked(checked)
			self.btn_stats_panel.blockSignals(False)
		self.stats_panel.setVisible(checked)
		self.save_app_settings()

	def toggle_location_density(self):
		new_mode = "none" if self.density_mode == "location" else "location"
		self.set_density_mode(new_mode)

	def toggle_population_density(self):
		new_mode = "none" if self.density_mode == "population" else "population"
		self.set_density_mode(new_mode)

	def toggle_fullscreen(self, checked):
		self.menuBar().setVisible(not checked)
		if checked:
			self.showFullScreen()
		else:
			self.showNormal()

	def toggle_stats_mode(self, checked):
		self.is_stats_mode = checked
		self.btn_stats_mode.setChecked(checked)
		self.act_stats_mode.setChecked(checked)
		self.combo_stats_hide.setVisible(checked)
		self.lbl_percentiles_to_hide.setVisible(checked)
		self.save_app_settings()
		self.redraw_current_plot()

	def toggle_year_offset(self, checked):
		self.is_year_offset = checked
		self.btn_year_offset.setChecked(checked)
		self.act_year_offset.setChecked(checked)
		self.save_app_settings()
		self.redraw_current_plot()

	def toggle_stats_shading_all(self, checked):
		self.stats_shading_all = checked
		if hasattr(self, 'act_stats_shading_all'):
			self.act_stats_shading_all.setChecked(checked)
		self.save_app_settings()
		if self.is_stats_mode:
			self.redraw_current_plot()

	def toggle_density(self, checked):
		if checked:
			rloc_map = log_parser.get_region_locations()
			has_country_locs = any(
				(r.get("locations", 0) or r.get("num_locations", 0) or 0) > 0
				for r in tg_cumulative_store.values()
			)
			has_region_locs = bool(rloc_map and any(v > 0 for v in rloc_map.values()))
			has_market_locs = any(
				(r.get("locations", 0) or 0) > 0
				for r in mk_cumulative_store.values()
			)

			is_country = bool(self.current_graph_info and self.current_graph_info['title'] in ("Country Metrics", "Credit Statistics"))
			is_market = bool(self.current_graph_info and self.current_graph_info['title'] == "Market Statistics")

			if is_country:
				has_locs = has_country_locs
			elif is_market:
				has_locs = has_market_locs
			else:
				has_locs = has_region_locs

			if not has_locs:
				QMessageBox.warning(
					self,
					"No Location Data",
					"There is no count of locations stored in the loaded logs.\n\n"
					"Density calculation requires location counts."
				)
				self.btn_density.setChecked(False)
				self.act_density.setChecked(False)
				self.is_density = False
				return

		self.is_density = checked
		self.btn_density.setChecked(checked)
		self.act_density.setChecked(checked)
		self.save_app_settings()
		self.redraw_current_plot()

	def toggle_log_scale(self, checked):
		self.is_log_scale = checked
		self.btn_log_scale.setChecked(checked)
		self.act_log_scale.setChecked(checked)
		self.save_app_settings()
		self.apply_plot_settings()

	def toggle_moving_average(self, checked):
		self.is_moving_average = checked
		self.btn_moving_avg.setChecked(checked)
		self.act_moving_avg.setChecked(checked)
		self.save_app_settings()
		self.redraw_current_plot()

	def set_baseline_mode(self, mode):
		self.baseline_mode = mode
		idx_map = {"none": 0, "ratio": 1, "difference": 2}
		if hasattr(self, 'combo_baseline'):
			self.combo_baseline.blockSignals(True)
			self.combo_baseline.setCurrentIndex(idx_map.get(mode, 0))
			self.combo_baseline.blockSignals(False)
		self.save_app_settings()
		self.redraw_current_plot()

	def handle_i_shortcut(self):
		cur = self.combo_baseline.currentIndex()
		self.set_baseline_mode("none" if cur == 1 else "ratio")

	def handle_shift_i_shortcut(self):
		cur = self.combo_baseline.currentIndex()
		self.set_baseline_mode("none" if cur == 2 else "difference")

	def toggle_bar_chart(self, checked):
		self.is_bar_chart = checked
		if self.btn_bar_chart.isChecked() != checked:
			self.btn_bar_chart.blockSignals(True)
			self.btn_bar_chart.setChecked(checked)
			self.btn_bar_chart.blockSignals(False)
		if self.act_bar_chart.isChecked() != checked:
			self.act_bar_chart.blockSignals(True)
			self.act_bar_chart.setChecked(checked)
			self.act_bar_chart.blockSignals(False)
		self._update_bar_chart_visibility()
		self.save_app_settings()
		self.redraw_current_plot()

	def handle_r_shortcut(self):
		cur = self.combo_derivative.currentIndex()
		if cur == 2:  # Acceleration -> Rate
			self.combo_derivative.setCurrentIndex(1)
		elif cur == 0:  # Base -> Rate
			self.combo_derivative.setCurrentIndex(1)
		else:  # Rate -> Base
			self.combo_derivative.setCurrentIndex(0)

	def handle_shift_r_shortcut(self):
		cur = self.combo_derivative.currentIndex()
		if cur == 2:  # Acceleration -> Base
			self.combo_derivative.setCurrentIndex(0)
		else:  # Base or Rate -> Acceleration
			self.combo_derivative.setCurrentIndex(2)

	def apply_plot_settings(self):
		if not (self.ax.get_lines() or self.ax.patches):
			return
		try:
			if self.is_log_scale:
				has_negative = False
				for line in self.ax.get_lines():
					y = line.get_ydata()
					if len(y) > 0 and np.any(np.asarray(y) < 0):
						has_negative = True
						break
				if not has_negative:
					for p in self.ax.patches:
						if p.get_y() < 0 or (p.get_height() is not None and p.get_height() < 0):
							has_negative = True
							break

				if has_negative:
					self.ax.set_yscale('symlog', linthresh=MINIMUM_NUMBER_FOR_LOG_PLOTS, linscale=1.0)
				else:
					self.ax.set_yscale('log', nonpositive='clip')
					ymin, ymax = self.ax.get_ylim()
					if ymin < MINIMUM_NUMBER_FOR_LOG_PLOTS and ymax > MINIMUM_NUMBER_FOR_LOG_PLOTS:
						self.ax.set_ylim(bottom=MINIMUM_NUMBER_FOR_LOG_PLOTS)
			else:
				self.ax.set_yscale('linear')
			self.canvas.draw_idle()
		except Exception:
			self.is_log_scale = False
			self.btn_log_scale.setChecked(False)
			self.act_log_scale.setChecked(False)
			self.ax.set_yscale('linear')
			self.canvas.draw_idle()

	def _update_bar_chart_visibility(self):
		combo_moment = self.filter_widget_map.get('moment')
		combo_from = self.filter_widget_map.get('from_year')
		combo_to = self.filter_widget_map.get('to_year')
		lbl_moment = self.filter_widget_map.get('lbl_moment')
		lbl_from = self.filter_widget_map.get('lbl_from_year')
		lbl_to = self.filter_widget_map.get('lbl_to_year')

		if self.is_bar_chart:
			if lbl_moment: lbl_moment.setVisible(True)
			if combo_moment:
				combo_moment.setVisible(True)
				if combo_moment.currentIndex() == 0 and combo_moment.count() > 1:
					combo_moment.blockSignals(True)
					combo_moment.setCurrentIndex(combo_moment.count() - 1)
					combo_moment.blockSignals(False)
			if lbl_from: lbl_from.setVisible(False)
			if combo_from:
				combo_from.blockSignals(True)
				combo_from.setCurrentIndex(0)
				combo_from.blockSignals(False)
				combo_from.setVisible(False)
			if lbl_to: lbl_to.setVisible(False)
			if combo_to:
				combo_to.blockSignals(True)
				combo_to.setCurrentIndex(0)
				combo_to.blockSignals(False)
				combo_to.setVisible(False)
		else:
			if lbl_moment: lbl_moment.setVisible(False)
			if combo_moment:
				combo_moment.blockSignals(True)
				combo_moment.setCurrentIndex(0)
				combo_moment.blockSignals(False)
				combo_moment.setVisible(False)
			if lbl_from: lbl_from.setVisible(True)
			if combo_from: combo_from.setVisible(True)
			if lbl_to: lbl_to.setVisible(True)
			if combo_to: combo_to.setVisible(True)

		self._update_view_year_dependencies()

	def _update_view_year_dependencies(self):
		combo_moment = self.filter_widget_map.get('moment')
		view_year_chosen = False
		if combo_moment is not None and combo_moment.currentIndex() > 0:
			view_year_chosen = True
		elif self.is_bar_chart:
			view_year_chosen = True

		show_time_series_controls = not view_year_chosen

		self.lbl_baseline.setVisible(show_time_series_controls)
		self.combo_baseline.setVisible(show_time_series_controls)
		self.combo_baseline.setEnabled(show_time_series_controls)

		self.btn_stats_mode.setVisible(show_time_series_controls)
		self.btn_stats_mode.setEnabled(show_time_series_controls)
		if hasattr(self, 'act_stats_mode'):
			self.act_stats_mode.setVisible(show_time_series_controls)
			self.act_stats_mode.setEnabled(show_time_series_controls)

		self.combo_stats_hide.setVisible(show_time_series_controls and self.is_stats_mode)
		self.lbl_percentiles_to_hide.setVisible(show_time_series_controls and self.is_stats_mode)
		self.lbl_derivative.setVisible(show_time_series_controls)
		self.combo_derivative.setVisible(show_time_series_controls)
		self.stats_panel.setVisible(self.is_stats_panel_visible)

	def on_plot_updated(self):
		self.cursor_hover_handler = InteractiveLineTooltip(
			self.ax,
			on_line_click_callback=self.handle_line_click,
			on_stats_hover_callback=self.update_stats_summary_panel
		)
		self.cursor_hover_handler.setup_tooltip_handler()
		self._update_view_year_dependencies()
		self.apply_plot_settings()

	def _on_stats_hide_changed(self, idx):
		self.stats_hide_idx = idx
		self.save_app_settings()
		self.redraw_current_plot()

	def _on_derivative_changed(self, idx):
		self.derivative_order = idx
		self.save_app_settings()
		self.redraw_current_plot()

	def _on_density_changed(self, idx):
		modes = ["none", "population", "location"]
		mode = modes[idx] if 0 <= idx < len(modes) else "none"
		self.set_density_mode(mode)

	def _on_baseline_changed(self, idx):
		modes = ["none", "ratio", "difference"]
		mode = modes[idx] if 0 <= idx < len(modes) else "none"
		self.set_baseline_mode(mode)