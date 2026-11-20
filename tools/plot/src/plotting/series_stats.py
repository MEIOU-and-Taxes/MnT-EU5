import numpy as np


def _calculate_series_stats(country_series, all_values, value_label):
	"""Helper to calculate consecutive deltas, overall deltas, volatility, and summary metrics."""
	consecutive_changes = []
	overall_changes = []
	entity_volatilities = []

	for ent, history in country_series.items():
		vals = list(history.values())
		if len(vals) >= 2:
			h_sorted = sorted(history.keys())
			entity_volatilities.append((
				ent,
				float(np.std(vals)),
				h_sorted[0],
				h_sorted[-1]
			))
			# Consecutive step deltas
			for i in range(len(h_sorted) - 1):
				y_from, y_to = h_sorted[i], h_sorted[i + 1]
				v_from, v_to = history[y_from], history[y_to]
				if v_from != 0 and v_to != 0:
					delta = v_to - v_from
					consecutive_changes.append((ent, delta, v_from, v_to, y_from, y_to))

			# Non-consecutive: find maximum rise and fall across all chronological pairs
			max_pos_delta = 0
			best_pos_pair = None
			max_neg_delta = 0
			best_neg_pair = None

			for i in range(len(h_sorted)):
				for j in range(i + 1, len(h_sorted)):
					y_i, y_j = h_sorted[i], h_sorted[j]
					v_i, v_j = history[y_i], history[y_j]
					if v_i == 0 or v_j == 0:
						continue
					d = v_j - v_i
					if d > max_pos_delta:
						max_pos_delta = d
						best_pos_pair = (ent, d, v_i, v_j, y_i, y_j)
					elif d < max_neg_delta:
						max_neg_delta = d
						best_neg_pair = (ent, d, v_i, v_j, y_i, y_j)

			if best_pos_pair:
				overall_changes.append(best_pos_pair)
			if best_neg_pair:
				overall_changes.append(best_neg_pair)

	return {
		"value_label": value_label,
		"biggest_increase": sorted(consecutive_changes, key=lambda x: x[1], reverse=True)[:5],
		"biggest_decrease": sorted(consecutive_changes, key=lambda x: x[1])[:5],
		"overall_increase": sorted([c for c in overall_changes if c[1] > 0], key=lambda x: x[1], reverse=True)[:5],
		"overall_decrease": sorted([c for c in overall_changes if c[1] < 0], key=lambda x: x[1])[:5],
		"most_volatile": sorted(entity_volatilities, key=lambda x: x[1], reverse=True)[:5],
		"overall_mean": float(np.mean(all_values)) if all_values else 0.0,
		"overall_std": float(np.std(all_values)) if all_values else 0.0
	}
