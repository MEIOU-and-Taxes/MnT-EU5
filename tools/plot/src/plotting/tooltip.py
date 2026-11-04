import numpy as np

from src.parsing.numeric_utils import format_metric_3digits

TOOLTIP_DISPLAYED_LINES = 25
LINE_WIDTH_SELECTED = 5
TOOLTIP_OPACITY = 0.75
TOOLTIP_PADDING = 20
TOOLTIP_PADDING_X = 40  # horizontal gap from the point (points)
TOOLTIP_PADDING_Y = 0  # vertical gap from the point (points)
TOOLTIP_FONT_SIZE = 10          # match annotate font size (default is 10)
TOOLTIP_CHAR_WIDTH_RATIO = 0.62 # monospace char width ≈ 0.6 * font size
TOOLTIP_LINE_HEIGHT_RATIO = 1.3
TOOLTIP_MARGIN = 20             # extra safety gap from the axes border (points)
TOOLTIP_UP_FRACTION = 0.6

class InteractiveLineTooltip:
    """Hover annotation and line inspection handler."""
    def __init__(self, ax, on_line_click_callback=None, on_stats_hover_callback=None):
        self.ax = ax
        self.fig = ax.figure
        self.on_line_click_callback = on_line_click_callback
        self.on_stats_hover_callback = on_stats_hover_callback

        self.original_line_widths = {}
        self.last_hovered_line = None
        self.lines = []

        for line in self.ax.get_lines():
            label = line.get_label()
            if label and not label.startswith('_'):
                self.lines.append(line)
                self.original_line_widths[label] = line.get_linewidth()

        self.last_integer_x = None
        self.closest_line = None
        self.tooltip_cache = None
        self.annot = None

    def setup_tooltip_handler(self):
        if not self.lines:
            return

        self.tooltip_cache = self.precalculate_tooltips()
        self.annot = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc="white", alpha=TOOLTIP_OPACITY),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
            fontfamily='monospace'
        )
        self.annot.set_visible(False)

        self.fig.canvas.mpl_connect("motion_notify_event", self.on_hover)
        self.fig.canvas.mpl_connect("axes_leave_event", self.on_leave)
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)

    def on_click(self, event):
        if event.inaxes != self.ax or event.button != 1 or not self.on_line_click_callback:
            return

        min_dist = float('inf')
        closest_label = None
        for line in self.lines:
            x_data, y_data = line.get_data()
            if not len(x_data):
                continue
            interp_y = np.interp(event.xdata, x_data, y_data)
            dist = abs(self.ax.transData.transform((event.xdata, interp_y))[1] - event.y)
            if dist < min_dist:
                min_dist = dist
                closest_label = line.get_label()

        if closest_label:
            self.on_line_click_callback(closest_label)

    def on_hover(self, event):
        if not hasattr(self, 'annot') or event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return

        # Dynamic Legend Relocation
        legend = getattr(self.ax, '_current_legend', None) or self.ax.get_legend()
        if legend is not None:
            xlim = self.ax.get_xlim()
            mid_x = (xlim[0] + xlim[1]) / 2.0
            # If mouse is on left half, anchor legend to upper right; if on right half, anchor to upper left
            desired_loc = "upper right" if event.xdata < mid_x else "upper left"
            if getattr(self.ax, '_last_legend_loc', 'upper left') != desired_loc:
                self.ax._last_legend_loc = desired_loc
                legend._set_loc(1 if desired_loc == "upper right" else 2)
                self.fig.canvas.draw_idle()

        # ---

        cur_x = int(round(event.xdata))
        min_dist = float('inf')
        closest_point = None
        current_hovered = None

        for line in self.lines:
            x_data, y_data = line.get_data()
            idx = np.searchsorted(x_data, cur_x)
            if idx < len(x_data) and x_data[idx] == cur_x:
                px, py = x_data[idx], y_data[idx]
                dist = abs(self.ax.transData.transform((px, py))[1] - event.y)
                if dist < min_dist:
                    min_dist = dist
                    closest_point = (px, py)
                    current_hovered = line

        if current_hovered != self.last_hovered_line:
            if self.last_hovered_line is not None:
                lbl = self.last_hovered_line.get_label()
                self.last_hovered_line.set_linewidth(self.original_line_widths.get(lbl, 1.5))
            if current_hovered is not None:
                current_hovered.set_linewidth(LINE_WIDTH_SELECTED)
            self.last_hovered_line = current_hovered
            self.fig.canvas.draw_idle()

        # Stats Mode handling
        moments_data = getattr(self.ax, '_stats_moments_data', None)
        global_stats = getattr(self.ax, '_global_stats', None)
        is_year_offset = getattr(self.ax, '_is_year_offset', False)
        year_offset = 1337 if is_year_offset else 0
        orig_x = cur_x + year_offset

        if moments_data and orig_x in moments_data:
            if self.on_stats_hover_callback:
                vals = [x[1] for x in moments_data[orig_x]]
                sorted_moments = sorted(moments_data.keys())
                cur_idx = sorted_moments.index(orig_x)
                prev_m = sorted_moments[cur_idx - 1] if cur_idx > 0 else None

                yearly_increase = []
                yearly_decrease = []
                if prev_m is not None:
                    prev_dict = dict(moments_data[prev_m])
                    cur_dict = dict(moments_data[orig_x])
                    step_deltas = []
                    for ent, val_cur in cur_dict.items():
                        if ent in prev_dict:
                            val_prev = prev_dict[ent]
                            # Exclude transitions to or from exactly 0
                            if val_prev != 0 and val_cur != 0:
                                delta = val_cur - val_prev
                                step_deltas.append((ent, delta, val_prev, val_cur))
                    yearly_increase = sorted(step_deltas, key=lambda x: x[1], reverse=True)[:3]
                    yearly_decrease = sorted(step_deltas, key=lambda x: x[1])[:3]

                self.on_stats_hover_callback(global_stats, {
                    "year": orig_x,
                    "prev_year": prev_m,
                    "mean": float(np.mean(vals)),
                    "median": float(np.median(vals)),
                    "std": float(np.std(vals)),
                    "count": len(vals),
                    "biggest_increase": yearly_increase,
                    "biggest_decrease": yearly_decrease
                })

            target_val, curve_label = None, ""
            min_curve_dist = float('inf')
            for line in self.lines:
                x, y = line.get_data()
                idx = np.searchsorted(x, cur_x)
                if idx < len(x) and x[idx] == cur_x:
                    dist = abs(self.ax.transData.transform((x[idx], y[idx]))[1] - event.y)
                    if dist < min_curve_dist:
                        min_curve_dist = dist
                        target_val = y[idx]
                        curve_label = line.get_label()

            if target_val is not None:
                closest_entries = sorted(moments_data[orig_x], key=lambda x: abs(x[1] - target_val))[:TOOLTIP_DISPLAYED_LINES]
                top_sorted = sorted(closest_entries, key=lambda x: x[1], reverse=True)
                top_formatted = [(ent, format_metric_3digits(v)) for ent, v in top_sorted]

                max_ent = max((len(str(ent)) for ent, _ in top_formatted), default=10)
                max_v = max((len(v_str) for _, v_str in top_formatted), default=6)

                year_hdr = f"Year: {cur_x}" if is_year_offset else f"Year: {cur_x}"
                header_label = f"{year_hdr} | {curve_label}"
                val_str = f"Val: {format_metric_3digits(target_val)}"
                sep_len = max(len(header_label), max_ent + max_v + 5, 30)

                lines = [header_label, val_str, "-" * sep_len]
                lines.extend([f"{v_str:>{max_v}} : {ent}" for ent, v_str in top_formatted])

                self._place_annotation(event, cur_x, target_val, "\n".join(lines))
            return

        # Normal Line Mode
        if cur_x == self.last_integer_x and self.closest_line == (current_hovered.get_label() if current_hovered else None):
            return
        self.last_integer_x = cur_x
        self.closest_line = current_hovered.get_label() if current_hovered else None

        cached = self.tooltip_cache.get(cur_x) if self.tooltip_cache else None
        if not cached or not closest_point:
            if self.annot.get_visible():
                self.annot.set_visible(False)
                self.fig.canvas.draw_idle()
            return

        for itm in cached:
            itm['dist'] = abs(itm['y_val'] - event.ydata)
        sorted_data = sorted(sorted(cached, key=lambda d: d['dist'])[:TOOLTIP_DISPLAYED_LINES], key=lambda d: d['y_val'], reverse=True)
        formatted_items = [(itm, format_metric_3digits(itm['y_val'])) for itm in sorted_data]

        max_lbl = max(len(itm['label']) for itm, _ in formatted_items)
        max_val = max(len(v_str) for _, v_str in formatted_items)

        text_lines = [f"{self.ax.get_xlabel() or 'X':>{max_lbl + 3}} : {cur_x}", ""]
        for itm, v_str in formatted_items:
            mark = '*' if itm['label'] == self.closest_line else ' '
            text_lines.append(f"{v_str:>{max_val}} : {mark}{itm['label']:<{max_lbl}}")

        self._place_annotation(event, closest_point[0], closest_point[1], "\n".join(text_lines))

    def _place_annotation(self, event, x, y, text):
        # Estimate tooltip size in points
        text_lines = text.split("\n")
        est_w = max(len(l) for l in text_lines) * TOOLTIP_FONT_SIZE * TOOLTIP_CHAR_WIDTH_RATIO
        est_h = len(text_lines) * TOOLTIP_FONT_SIZE * TOOLTIP_LINE_HEIGHT_RATIO
        est_w += TOOLTIP_PADDING * 2 + TOOLTIP_MARGIN
        est_h += TOOLTIP_PADDING * 2 + TOOLTIP_MARGIN

        # Convert to pixels and compare against the axes bounds
        px_per_pt = self.fig.dpi / 72.0
        bbox = self.ax.bbox
        room_right = bbox.x1 - event.x
        room_above = bbox.y1 - event.y
        room_below = event.y - bbox.y0
        est_h_px = est_h * px_per_pt

        h_align = 'left' if room_right >= est_w * px_per_pt else 'right'

        # Prefer upward; only go downward if upward is cramped AND below has more room
        if room_above >= est_h_px * TOOLTIP_UP_FRACTION or room_above >= room_below:
            v_align = 'bottom'
        else:
            v_align = 'top'

        h_offset = TOOLTIP_PADDING if h_align == 'left' else -TOOLTIP_PADDING
        v_offset = TOOLTIP_PADDING if v_align == 'bottom' else -TOOLTIP_PADDING

        self.annot.set_verticalalignment(v_align)
        self.annot.set_horizontalalignment(h_align)
        self.annot.xyann = (h_offset, v_offset)
        self.annot.set_text(text)
        self.annot.xy = (x, y)
        self.annot.set_visible(True)
        self.fig.canvas.draw_idle()

    def on_leave(self, event):
        if self.last_hovered_line is not None:
            lbl = self.last_hovered_line.get_label()
            self.last_hovered_line.set_linewidth(self.original_line_widths.get(lbl, 1.5))
            self.last_hovered_line = None
            self.fig.canvas.draw_idle()
        if hasattr(self, 'annot') and self.annot.get_visible():
            self.annot.set_visible(False)
            self.fig.canvas.draw_idle()

    def precalculate_tooltips(self):
        if not self.lines:
            return {}
        all_x = np.concatenate([line.get_xdata() for line in self.lines])
        if all_x.size == 0:
            return {}
        cache = {}
        for x_val in range(int(np.min(all_x)), int(np.max(all_x)) + 1):
            pts = []
            for line in self.lines:
                x_d, y_d = line.get_data()
                idx = np.searchsorted(x_d, x_val)
                if idx < len(x_d) and x_d[idx] == x_val:
                    pts.append({'label': line.get_label(), 'y_val': y_d[idx]})
            if pts:
                pts.sort(key=lambda item: item['y_val'], reverse=True)
                cache[x_val] = pts
        return cache