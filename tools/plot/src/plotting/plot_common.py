MARGIN_BETWEEN_BORDERS_AND_OUTER_DATA_POINTS = 0

def _draw_horizontal_axis(ax):
	"""Draws horizontal grid lines after every number on the y-axis and a zero line."""
	ax.spines['bottom'].set_visible(True)
	ax.set_axisbelow(True)
	# Horizontal line across every number on the left (y) axis
	ax.yaxis.grid(True, linestyle='--', linewidth=0.7, color='#cccccc', alpha=0.7)

	y_min, y_max = ax.get_ylim()
	if y_min <= 0 <= y_max:
		linestyle = '--' if (y_min < 0 and y_max > 0) else '-'
		ax.axhline(0, color='#666666', linewidth=0.8, linestyle=linestyle, alpha=0.75, zorder=1)
