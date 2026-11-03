from itertools import cycle
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from PyQt6.QtWidgets import QLabel
from matplotlib.ticker import MaxNLocator

from src.constants import (
    STR_ALL_MOMENTS, STR_ALL_REGIONS, STAT_COLORS,
    POS_SUBPLOT_BOTTOM_EDGE, POS_SUBPLOT_RIGHT_EDGE, SHOW_LEGEND,
    ERROR_NO_DATA_MATCH
)
from src.plotting.configs import BT_CONFIG, GP_CONFIG, MK_CONFIG, POP_CONFIG, RT_CONFIG, CM_CONFIG
from src.widgets.custom_combobox import RightClickableComboBox


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


def _create_generic_graph(
    data,
    ax,
    filter_layout,
    filter_widgets_list,
    on_lines_plotted,
    on_plot_cleared,
    filter_widget_map,
    get_is_moving_avg,
    get_period_value,
    get_is_stats_mode=lambda: False,
    on_stats_computed=None,
    get_stats_bands=lambda: 5,
    set_redraw_fn=None,
    *,
    config  # <-- Keyword-only argument prevents positional collision
):
    all_data = config["parser"](data)
    fig = ax.figure
    fig.subplots_adjust(bottom=POS_SUBPLOT_BOTTOM_EDGE, right=POS_SUBPLOT_RIGHT_EDGE)

    category_key = config["category_key"]
    value_key = config["value_key"]
    category_label_str = config["category_label"]
    all_category_str = config["all_category_str"]
    value_label_str = config["value_label"]
    add_zero_start = config.get("add_zero_start", False)
    has_region = config.get("has_region_filter", True)

    # Time dropdown
    lbl_moment = QLabel("Time:")
    combo_moment = RightClickableComboBox()
    all_moments = sorted(list(set(item['moment'] for item in all_data)))
    combo_moment.addItem(STR_ALL_MOMENTS)
    combo_moment.addItems([str(m) for m in all_moments])
    filter_widget_map['moment'] = combo_moment

    # Category / Metric dropdown
    lbl_category = QLabel(category_label_str)
    combo_category = RightClickableComboBox()
    all_categories = sorted(list(set(item[category_key] for item in all_data)))
    if all_category_str:
        combo_category.addItem(all_category_str)
    combo_category.addItems(all_categories)
    filter_widget_map[category_key] = combo_category

    filter_layout.addWidget(lbl_moment, 0, 0)
    filter_layout.addWidget(combo_moment, 0, 1)
    filter_layout.addWidget(lbl_category, 0, 2)
    filter_layout.addWidget(combo_category, 0, 3)
    filter_widgets_list.extend([lbl_moment, combo_moment, lbl_category, combo_category])

    # Optional Region / Country dropdown (only for charts with has_region = True)
    combo_region = None
    if has_region:
        lbl_region = QLabel("Region:")
        combo_region = RightClickableComboBox()
        all_regions = sorted(list(set(item.get('region') or item.get('country') for item in all_data)))
        combo_region.addItem(STR_ALL_REGIONS)
        combo_region.addItems(all_regions)
        filter_widget_map['region'] = combo_region

        filter_layout.addWidget(lbl_region, 0, 4)
        filter_layout.addWidget(combo_region, 0, 5)
        filter_layout.setColumnStretch(6, 1)
        filter_widgets_list.extend([lbl_region, combo_region])
    else:
        filter_layout.setColumnStretch(4, 1)

    def update_plot():
        on_plot_cleared()
        m_filter = combo_moment.currentText()
        c_filter = combo_category.currentText()
        r_filter = combo_region.currentText() if combo_region else STR_ALL_REGIONS
        ax.clear()

        if has_region and all_category_str and c_filter != all_category_str and r_filter != STR_ALL_REGIONS:
            ax.text(0.5, 0.5, f"Please select a specific {category_label_str.replace(':', '')} OR a Region, not both.",
                    ha='center', va='center')
            ax.figure.canvas.draw_idle()
            return

        pre_filtered = [
            item for item in all_data
            if (m_filter == STR_ALL_MOMENTS or item['moment'] == int(m_filter)) and
               (c_filter == all_category_str or c_filter == item.get(category_key)) and
               (r_filter == STR_ALL_REGIONS or r_filter == (item.get('region') or item.get('country')))
        ]
        filtered = [i for i in pre_filtered if i[value_key] != 0] if config.get("ignore_zeros") else pre_filtered

        if not filtered:
            ax.text(0.5, 0.5, ERROR_NO_DATA_MATCH, ha='center', va='center')
            ax.figure.canvas.draw_idle()
            if on_stats_computed:
                on_stats_computed(None)
            return

        is_r_picked = (r_filter != STR_ALL_REGIONS)
        entity_key = category_key if is_r_picked else ('country' if 'country' in filtered[0] else 'region')
        display_title = r_filter if is_r_picked else c_filter

        if get_is_stats_mode() and m_filter == STR_ALL_MOMENTS:
            _render_stats_mode(ax, filtered, value_key, value_label_str, display_title, entity_key,
                               get_stats_bands(), on_stats_computed, on_lines_plotted)
            return

        _render_standard_mode(ax, filtered, m_filter, c_filter, r_filter, all_category_str,
                              category_key, value_key, value_label_str, add_zero_start,
                              get_is_moving_avg, get_period_value, config, on_stats_computed, on_lines_plotted)

    if set_redraw_fn:
        set_redraw_fn(update_plot)

    combo_moment.currentIndexChanged.connect(update_plot)
    combo_category.currentIndexChanged.connect(update_plot)
    if combo_region:
        combo_region.currentIndexChanged.connect(update_plot)
    update_plot()


def _render_stats_mode(ax, filtered_data, value_key, value_label, display_title, entity_key, num_bands, on_stats_computed, on_lines_plotted):
    moments_dict = {}
    country_series = {}
    for item in filtered_data:
        m = item['moment']
        val = item[value_key]
        ent = item.get(entity_key, item.get('region', ''))
        moments_dict.setdefault(m, []).append((ent, val))
        country_series.setdefault(ent, {})[m] = val

    sorted_moments = sorted(moments_dict.keys())
    bands_map = {
        9: [("Max", 100), ("99th Perc", 99), ("95th Perc", 95), ("75th Perc", 75), ("Median", 50), ("25th Perc", 25), ("5th Perc", 5), ("1st Perc", 1), ("Min", 0)],
        7: [("Max", 100), ("95th Perc", 95), ("75th Perc", 75), ("Median", 50), ("25th Perc", 25), ("5th Perc", 5), ("Min", 0)],
        5: [("Max", 100), ("75th Perc", 75), ("Median", 50), ("25th Perc", 25), ("Min", 0)]
    }
    active_percentiles = bands_map.get(num_bands, bands_map[5])
    stat_curves = {name: [] for name, _ in active_percentiles}

    for m in sorted_moments:
        vals = sorted([x[1] for x in moments_dict[m]])
        for name, p in active_percentiles:
            if p == 100: stat_curves[name].append(vals[-1])
            elif p == 0: stat_curves[name].append(vals[0])
            elif p == 50: stat_curves[name].append(float(np.median(vals)))
            else: stat_curves[name].append(float(np.percentile(vals, p)))

    ax._stats_moments_data = moments_dict

    changes = []
    for ent, history in country_series.items():
        if len(history) >= 2:
            h_sorted = sorted(history.keys())
            delta = history[h_sorted[-1]] - history[h_sorted[0]]
            changes.append((ent, delta, history[h_sorted[0]], history[h_sorted[-1]], np.std(list(history.values()))))

    all_values = [i[value_key] for i in filtered_data]
    global_stats = {
        "value_label": value_label,
        "biggest_increase": sorted(changes, key=lambda x: x[1], reverse=True)[:3],
        "biggest_decrease": sorted(changes, key=lambda x: x[1])[:3],
        "most_volatile": sorted(changes, key=lambda x: x[4], reverse=True)[:3],
        "overall_mean": np.mean(all_values),
        "overall_std": np.std(all_values)
    }
    ax._global_stats = global_stats

    for name, _ in active_percentiles:
        ax.plot(sorted_moments, stat_curves[name], marker='o', linewidth=2, label=name, color=STAT_COLORS[name])

    ax.fill_between(sorted_moments, stat_curves["25th Perc"], stat_curves["75th Perc"], color="#8bc34a", alpha=0.15, label='IQR (25%-75%)')
    ax.fill_between(sorted_moments, stat_curves["Min"], stat_curves["Max"], color="#2e7d32", alpha=0.04)

    ax.set_xlabel("Time")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.ticklabel_format(useOffset=False, style='plain', axis='x')
    ax.set_ylabel(value_label)
    ax.set_title(f"Statistical Distribution: {display_title}")
    ax.legend(loc="upper left", ncol=2 if num_bands > 5 else 1, fontsize=9, framealpha=0.85)

    _draw_horizontal_axis(ax)

    if on_stats_computed:
        on_stats_computed(global_stats)

    ax.figure.canvas.draw_idle()
    on_lines_plotted()


def _render_standard_mode(ax, filtered_data, m_filter, c_filter, r_filter, all_cat,
                          cat_key, val_key, val_label, add_zero, get_is_moving_avg, get_period,
                          config, on_stats_computed, on_lines_plotted):
    ax._stats_moments_data = None
    ax._global_stats = None
    if on_stats_computed:
        on_stats_computed(None)

    is_m_all = m_filter == STR_ALL_MOMENTS
    is_c_picked = c_filter != all_cat
    is_r_picked = r_filter != STR_ALL_REGIONS
    colors = cycle(plt.rcParams['axes.prop_cycle'].by_key()['color'])

    if is_m_all and (is_c_picked or is_r_picked):
        plot_key = cat_key if is_r_picked else 'region'
        series = {}
        for item in filtered_data:
            ent = item.get(plot_key, '')
            series.setdefault(ent, {'m': [], 'v': []})
            series[ent]['m'].append(item['moment'])
            series[ent]['v'].append(item[val_key])

        if add_zero and series:
            all_m = [moment for v in series.values() for moment in v['m']]
            if all_m:
                overall_min_m = min(all_m)
                for values in series.values():
                    if values['m']:
                        line_min_m = min(values['m'])
                        if line_min_m > overall_min_m:
                            values['m'].append(line_min_m - 1)
                            values['v'].append(0)

        ax.set_xlabel("Time")
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_ylabel(val_label)
        ax.set_title(f"{val_label}s for: {c_filter}" if is_c_picked else f"{val_label}s in: {r_filter}")

        marker = 'o' if len(set(i['moment'] for i in filtered_data)) <= 50 else None
        is_ma = get_is_moving_avg()
        p = get_period()

        for name, vals in sorted(series.items()):
            sm, sv = zip(*sorted(zip(vals['m'], vals['v'])))
            if is_ma and len(sv) > 1:
                ma_vals = [sum(sv[max(0, i-p+1):i+1]) / len(sv[max(0, i-p+1):i+1]) for i in range(len(sv))]
                ax.plot(sm, ma_vals, linestyle='-', label=name, color=next(colors))
            else:
                ax.plot(sm, sv, marker=marker, linestyle='-', label=name, color=next(colors))

        if series:
            min_x = min(min(v['m']) for v in series.values() if v['m'])
            max_x = max(max(v['m']) for v in series.values() if v['m'])
            ax.set_xlim(min_x, max_x)
        if "y_axis_limits" in config:
            ax.set_ylim(config["y_axis_limits"])
        if SHOW_LEGEND:
            ax.legend(bbox_to_anchor=(1.04, 1), loc="upper left")

    elif not is_m_all and (is_c_picked or is_r_picked):
        color_key = cat_key if is_r_picked else 'region'
        items = sorted(list(set(i.get(color_key, '') for i in filtered_data)))
        cmap = {n: next(colors) for n in items}
        labels = [str(i.get(cat_key if is_r_picked else 'region', '')) for i in filtered_data]
        values = [i[val_key] for i in filtered_data]
        b_colors = [cmap[i.get(color_key, '')] for i in filtered_data]

        ax.bar(labels, values, color=b_colors)
        ax.set_ylabel(val_label)
        ax.set_title(f"{val_label}s for Month: {m_filter}")
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

        if items:
            patches = [mpatches.Patch(color=c, label=l) for l, c in cmap.items()]
            ax.legend(handles=patches, bbox_to_anchor=(1.04, 1), loc="upper left")
    else:
        ax.text(0.5, 0.5, "Please select a filter to display a graph.", ha='center', va='center')

    _draw_horizontal_axis(ax)

    ax.figure.canvas.draw_idle()
    on_lines_plotted()


# --- Chart entry wrappers ---
def graph_building_types(*args, **kwargs):
    """Building Types by Region"""
    kwargs["config"] = BT_CONFIG
    _create_generic_graph(*args, **kwargs)

def graph_goods_prices(*args, **kwargs):
    """Goods Prices by Region"""
    kwargs["config"] = GP_CONFIG
    _create_generic_graph(*args, **kwargs)

def graph_markets(*args, **kwargs):
    """Market Statistics"""
    kwargs["config"] = MK_CONFIG
    _create_generic_graph(*args, **kwargs)

def graph_population(*args, **kwargs):
    """Population by Region"""
    kwargs["config"] = POP_CONFIG
    _create_generic_graph(*args, **kwargs)

def graph_road_types(*args, **kwargs):
    """Road Coverage by Region"""
    kwargs["config"] = RT_CONFIG
    _create_generic_graph(*args, **kwargs)

def graph_country_metrics(*args, **kwargs):
    """Country Metrics"""
    kwargs["config"] = CM_CONFIG
    _create_generic_graph(*args, **kwargs)