import json
import os

from src.constants import SETTINGS_PATH


class SettingsStore:
	def load_app_settings(self):
		if not os.path.exists(SETTINGS_PATH):
			return
		try:
			with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
				data = json.load(f)
			self.refresh_interval_idx = data.get("refresh_interval_idx", 0)
			self.autosave_interval_idx = data.get("autosave_interval_idx", 1)
			self.period_value = data.get("period_value", 5)
			self.is_stats_mode = data.get("is_stats_mode", True)
			self.stats_hide_idx = data.get("stats_hide_idx", 0)
			self.density_mode = data.get("density_mode", "location" if data.get("is_density", False) else "none")
			self.derivative_order = data.get("derivative_order", 1 if data.get("is_rate", False) else 0)
			self.baseline_mode = data.get("baseline_mode", "ratio" if data.get("is_ratio_mode", False) else "none")
			self.is_bar_chart = data.get("is_bar_chart", False)
			self.is_year_offset = data.get("is_year_offset", False)
			self.is_ratio_mode = data.get("is_ratio_mode", False)
			self.is_log_scale = data.get("is_log_scale", False)
			self.is_moving_average = data.get("is_moving_average", False)
			self.stats_shading_all = data.get("stats_shading_all", True)
			self.is_stats_panel_visible = data.get("is_stats_panel_visible", True)
		except Exception as e:
			print(f"Failed to load settings from {SETTINGS_PATH}: {e}")


	def save_app_settings(self):
		try:
			data = {
				"refresh_interval_idx": self.refresh_interval_idx,
				"autosave_interval_idx": self.autosave_interval_idx,
				"period_value": self.period_value,
				"is_stats_mode": self.is_stats_mode,
				"stats_hide_idx": self.combo_stats_hide.currentIndex() if hasattr(self, 'combo_stats_hide') else self.stats_hide_idx,
				"density_mode": self.density_mode,
				"derivative_order": self.combo_derivative.currentIndex() if hasattr(self, 'combo_derivative') else self.derivative_order,
				"baseline_mode": self.baseline_mode,
				"is_bar_chart": self.is_bar_chart,
				"is_year_offset": self.is_year_offset,
				"is_log_scale": self.is_log_scale,
				"is_moving_average": self.is_moving_average,
				"stats_shading_all": self.stats_shading_all,
				"is_stats_panel_visible": self.is_stats_panel_visible,
			}
			with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
				json.dump(data, f, indent=2)
		except Exception as e:
			print(f"Failed to save settings to {SETTINGS_PATH}: {e}")