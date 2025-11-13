import numpy as np

TOOLTIP_PADDING = 20
TOOLTIP_DISPLAYED_LINES = 25
LINE_WIDTH_SELECTED = 5

class InteractiveLineTooltip:
	"""
	Creates a hover annotation for a Matplotlib axes that shows the
	Y-values of all lines at the current X-position of the cursor.
	"""

	def __init__(self, ax):
		self.ax = ax
		self.fig = ax.figure
		print(f"CursorHoverInfo: Initializing for axes: {ax}")

		all_lines = self.ax.get_lines()
		print(f"CursorHoverInfo: Found {len(all_lines)} total line objects in the axes.")

		# Store original line properties and track the last hovered line
		self.original_line_widths = {}
		self.last_hovered_line = None

		# Filter for lines that have a valid label for the legend
		self.lines = []
		for line in all_lines:
			label = line.get_label()
			if label and not label.startswith('_'):
				self.lines.append(line)
				self.original_line_widths[label] = line.get_linewidth()

		self.last_integer_x = None
		self.closest_line = None
		self.tooltip_cache = None
		self.annot = None
		self.cursor_hover_handler = None

		print(f"CursorHoverInfo: Kept {len(self.lines)} lines with valid labels.")

	def setup_tooltip_handler(self):
		"""Creates a new tooltip handler for the current axes."""
		print("\n--- Main window is creating tooltip handler ---")

		# If there are no valid lines, do not set up the hover events
		if not self.lines:
			print("CursorHoverInfo: No valid lines found. Tooltip will NOT be activated.")
			return

		self.tooltip_cache = self.precalculate_tooltips()

		# Create an annotation object, initially invisible
		self.annot = self.ax.annotate(
			"",
			xy=(0, 0),
			xytext=(15, 15),
			textcoords="offset points",
			bbox=dict(boxstyle="round,pad=0.5", fc="white", alpha=0.75),
			arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
			fontfamily='monospace',
		)
		self.annot.set_visible(False)

		# Connect the event handlers
		print("CursorHoverInfo: Activating tooltip event handlers.")
		self.fig.canvas.mpl_connect("motion_notify_event", self.on_hover)
		self.fig.canvas.mpl_connect("axes_leave_event", self.on_leave)

	def clear_tooltip_handler(self):
		"""Clears any existing tooltip handler."""
		self.cursor_hover_handler = None

	def on_hover(self, event):
		if not hasattr(self, 'annot') or event.inaxes != self.ax or event.xdata is None or event.ydata is None:
			return

		current_integer_x = int(round(event.xdata))
		min_vertical_dist = float('inf')
		closest_line_label = None
		closest_point_on_line = None
		current_hovered_line = None

		# Find the closest point on each line to anchor the tooltip arrow
		for line in self.lines:
			x_data, y_data = line.get_data()

			# Find the index for the current integer year
			idx = np.searchsorted(x_data, current_integer_x)
			if idx < len(x_data) and x_data[idx] == current_integer_x:
				point_x, point_y = x_data[idx], y_data[idx]

				# Calculate the vertical distance in screen pixels to find the closest line
				vertical_dist_pixels = abs(self.ax.transData.transform((point_x, point_y))[1] - event.y)

				# Check if this line is the new closest
				if vertical_dist_pixels < min_vertical_dist:
					min_vertical_dist = vertical_dist_pixels
					closest_line_label = line.get_label()
					closest_point_on_line = (point_x, point_y)
					current_hovered_line = line

		# Check if the hovered line has changed since the last event
		if current_hovered_line != self.last_hovered_line:
			# If there was a previously hovered line, reset its width
			if self.last_hovered_line is not None:
				label = self.last_hovered_line.get_label()
				original_width = self.original_line_widths.get(label)
				self.last_hovered_line.set_linewidth(original_width)

			# If hovering over a new line
			if current_hovered_line is not None:
				current_hovered_line.set_linewidth(LINE_WIDTH_SELECTED)

			# Update the last hovered line and redraw the canvas
			self.last_hovered_line = current_hovered_line
			self.fig.canvas.draw_idle()

		if current_integer_x == self.last_integer_x and self.closest_line == closest_line_label:
			return
		self.last_integer_x = current_integer_x
		self.closest_line = closest_line_label

		# Get all data for current X value
		all_data_for_x = self.tooltip_cache.get(current_integer_x)
		if not all_data_for_x:
			if self.annot.get_visible(): self.annot.set_visible(False); self.fig.canvas.draw_idle()
			return

		# Filter to X closest lines
		# Calculate each line's vertical distance from the cursor's data coordinate
		for item in all_data_for_x:
			item['dist_from_cursor'] = abs(item['y_val'] - event.ydata)

		# Sort by that distance to find the nearest lines
		all_data_for_x.sort(key=lambda d: d['dist_from_cursor'])

		# Take the X closest and then re-sort them by Y-value for display
		sorted_data = all_data_for_x[:TOOLTIP_DISPLAYED_LINES]
		sorted_data.sort(key=lambda d: d['y_val'], reverse=True)

		if not closest_point_on_line:
			if self.annot.get_visible(): self.annot.set_visible(False); self.fig.canvas.draw_idle()
			return

		# Build tooltip text
		x_label = self.ax.get_xlabel() or "X-Value"
		max_label_len = max(len(d['label']) for d in sorted_data) if sorted_data else 0
		max_val_len = max(len(f"{d['y_val']:,.2f}") for d in sorted_data) if sorted_data else 0

		info_texts = [f"{x_label:>{max_label_len + 3}} : {current_integer_x}", '']
		for item in sorted_data:
			label_str = f"{item['label']:<{max_label_len}}"
			val_str = f"{item['y_val']:>{max_val_len},.2f}"
			char_reveal = '*' if item['label'] == closest_line_label else ' '
			info_texts.append(f"{val_str} : {char_reveal}{label_str}")

		# Dynamic positioning with vertical alignment
		y_min, y_max = self.ax.get_ylim()
		y_mid = (y_min + y_max) * 0.4

		# If cursor is in the top half, place tooltip below the anchor point
		# The offset will push the text box down
		if event.ydata > y_mid:
			self.annot.set_verticalalignment('top')
			vertical_offset = -TOOLTIP_PADDING
		else:
			self.annot.set_verticalalignment('bottom')
			vertical_offset = TOOLTIP_PADDING

		# Horizontal positioning logic
		x_min, x_max = self.ax.get_xlim()
		x_mid = (x_min + x_max) * 0.7
		# If cursor is on the right, align text to the right and use a negative offset
		if event.xdata > x_mid:
			self.annot.set_horizontalalignment('right')
			horizontal_offset = -TOOLTIP_PADDING
		else:
			self.annot.set_horizontalalignment('left')
			horizontal_offset = TOOLTIP_PADDING

		# Set the final combined offset
		self.annot.xytext = (horizontal_offset, vertical_offset)

		# Update annotation
		self.annot.set_text("\n".join(info_texts))
		self.annot.xy = closest_point_on_line
		self.annot.set_visible(True)
		self.fig.canvas.draw_idle()

	def on_leave(self, event):
		if self.last_hovered_line is not None:
			label = self.last_hovered_line.get_label()
			original_width = self.original_line_widths.get(label)
			self.last_hovered_line.set_linewidth(original_width)
			self.last_hovered_line = None
			self.fig.canvas.draw_idle()

		if hasattr(self, 'annot') and self.annot.get_visible():
			self.annot.set_visible(False)
			self.fig.canvas.draw_idle()

	def precalculate_tooltips(self):
		"""
		Processes the plotted lines to create a cache of sorted data for every year, to avoid recalculating data on every mouse movement
		"""
		print("CursorHoverInfo: Pre-calculating tooltip data... ", end="")
		cache = {}
		if not self.lines: return {}
		all_x_data = np.concatenate([line.get_xdata() for line in self.lines])
		if all_x_data.size == 0:
			print("No data points found.")
			return {}
		min_x, max_x = int(np.min(all_x_data)), int(np.max(all_x_data))
		for x_val in range(min_x, max_x + 1):
			x_val_data = []
			for line in self.lines:
				x_data, y_data = line.get_data()
				idx = np.searchsorted(x_data, x_val)
				if idx < len(x_data) and x_data[idx] == x_val:
					x_val_data.append({'label': line.get_label(), 'y_val': y_data[idx]})
			if x_val_data:
				x_val_data.sort(key=lambda item: item['y_val'], reverse=True)
				cache[x_val] = x_val_data
		print("Done.")
		return cache
