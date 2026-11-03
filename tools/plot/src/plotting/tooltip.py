import numpy as np

TOOLTIP_PADDING = 20
TOOLTIP_DISPLAYED_LINES = 25
LINE_WIDTH_SELECTED = 5

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
            bbox=dict(boxstyle="round,pad=0.5", fc="white", alpha=0.75),
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

        if moments_data and cur_x in moments_data:
            if self.on_stats_hover_callback:
                vals = [x[1] for x in moments_data[cur_x]]
                self.on_stats_hover_callback(global_stats, {
                    "year": cur_x, "mean": float(np.mean(vals)),
                    "median": float(np.median(vals)), "std": float(np.std(vals)),
                    "count": len(vals)
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
                top_10 = sorted(moments_data[cur_x], key=lambda x: abs(x[1] - target_val))[:10]
                fmt = ",.0f" if (self.ax.get_ylabel() or "") in ("Population", "Count") else ",.2f"
                lines = [f"Year: {cur_x} | Curve: {curve_label}", f"Val: {target_val:{fmt}}", "-"*35]
                lines.extend([f"{v:>10{fmt}} : {ent}" for ent, v in top_10])

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

        fmt = ",.0f" if (self.ax.get_ylabel() or "") in ("Population", "Count") else ",.2f"
        max_lbl = max(len(d['label']) for d in sorted_data)
        max_val = max(len(f"{d['y_val']:{fmt}}") for d in sorted_data)

        text_lines = [f"{self.ax.get_xlabel() or 'X':>{max_lbl + 3}} : {cur_x}", ""]
        for itm in sorted_data:
            mark = '*' if itm['label'] == self.closest_line else ' '
            text_lines.append(f"{itm['y_val']:>{max_val}{fmt}} : {mark}{itm['label']:<{max_lbl}}")

        self._place_annotation(event, closest_point[0], closest_point[1], "\n".join(text_lines))

    def _place_annotation(self, event, x, y, text):
        y_min, y_max = self.ax.get_ylim()
        x_min, x_max = self.ax.get_xlim()
        v_align = 'top' if event.ydata > (y_min + (y_max - y_min) * 0.4) else 'bottom'
        h_align = 'right' if event.xdata > (x_min + (x_max - x_min) * 0.7) else 'left'
        v_offset = -TOOLTIP_PADDING if v_align == 'top' else TOOLTIP_PADDING
        h_offset = -TOOLTIP_PADDING if h_align == 'right' else TOOLTIP_PADDING

        self.annot.set_verticalalignment(v_align)
        self.annot.set_horizontalalignment(h_align)
        self.annot.xytext = (h_offset, v_offset)
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