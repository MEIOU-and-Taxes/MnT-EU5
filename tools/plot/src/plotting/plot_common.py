from PyQt6.QtGui import QCursor

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


def relocate_legend_out_of_way(ax, fig, cursor_x=None):
	legend = getattr(ax, '_current_legend', None) or ax.get_legend()
	if legend is None:
		return

	xlim = ax.get_xlim()
	mid_x = (xlim[0] + xlim[1]) / 2.0

	if cursor_x is None:
		try:
			from PyQt6.QtGui import QCursor
			pos = fig.canvas.mapFromGlobal(QCursor.pos())
			mpl_x = pos.x()
			mpl_y = fig.canvas.height() - pos.y()
			if ax.bbox.contains(mpl_x, mpl_y):
				inv = ax.transData.inverted()
				cursor_x = inv.transform((mpl_x, mpl_y))[0]
		except Exception:
			pass

	if cursor_x is not None:
		desired_loc = "upper right" if cursor_x < mid_x else "upper left"
	else:
		desired_loc = getattr(ax, '_last_legend_loc', 'upper left')

	ax._last_legend_loc = desired_loc
	legend._set_loc(1 if desired_loc == "upper right" else 2)