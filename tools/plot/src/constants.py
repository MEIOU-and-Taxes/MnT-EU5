REFRESH_PERIOD_MS = 5 * 1000
AUTOSAVE_PERIOD_MS = 5 * 60 * 1000
TARGET_FILE_NAME_ROOT = 'error'
AUTOSAVE_FILE = "autosave_session.dat"
ICON_PATH = 'icon.png'

IS_LOGGING_YEARLY = True
FIRST_MOMENT = 1 + 1337 if IS_LOGGING_YEARLY else 4

POS_SUBPLOT_BOTTOM_EDGE = 0.10
POS_SUBPLOT_RIGHT_EDGE = 0.95
SHOW_LEGEND = False

STR_ALL_MOMENTS = "All moments"
STR_ALL_BUILDINGS = "All buildings"
STR_ALL_REGIONS = "All regions"
STR_ALL_GOODS = "All goods"
STR_ALL_ROAD_TYPES = "All road types"

ERROR_FILE_NOT_FOUND = f'{TARGET_FILE_NAME_ROOT}.log not found. Please set the log folder.'
ERROR_NO_DATA_MATCH = "No data matches the current filters"
ERROR_NO_STATISTICS = "The logs exist, but there are no statistics stored\nPlay more or get other logs"

# Statistical Mode Color Scheme
STAT_COLORS = {
    "Max": "#1b5e20",        # Dark Green
    "99th Perc": "#2e7d32",   # Forest Green
    "95th Perc": "#4caf50",   # Green
    "75th Perc": "#8bc34a",   # Yellow-Green
    "Median": "#fbc02d",      # Gold / Yellow
    "25th Perc": "#fb8c00",   # Orange
    "5th Perc": "#f4511e",    # Coral / Light Red
    "1st Perc": "#c62828",    # Crimson
    "Min": "#b71c1c",         # Dark Red
}

GRAPH_INTRODUCTION = """
Welcome to the M&T graphing tool!

Press '`' to see the list of available graphs.
Refresh to read game.log again.

If this is the first run, update the generated config file
in the same folder & restart.
"""