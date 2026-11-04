import os

APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'MnT_Plotter')
os.makedirs(APPDATA_DIR, exist_ok=True)

KEY_CONFIGS_PATH = os.path.join(APPDATA_DIR, "key_configs.json")
SETTINGS_PATH = os.path.join(APPDATA_DIR, "settings.json")
AUTOSAVE_DIR = os.path.join(APPDATA_DIR, "autosaves")
os.makedirs(AUTOSAVE_DIR, exist_ok=True)

FILE_CHECK_PERIOD_MS = 1 * 1000
REFRESH_PERIOD_MS = FILE_CHECK_PERIOD_MS
AUTOSAVE_PERIOD_MS = 5 * 60 * 1000
TARGET_FILE_NAME_ROOT = 'error'
AUTOSAVE_FILE = os.path.join(AUTOSAVE_DIR, "autosave_session.dat")
ICON_PATH = 'icon.png'
AUTOSAVES_KEPT = 1
PRESETS_PER_PAGE = 10

IS_LOGGING_YEARLY = True
FIRST_MOMENT = 1 + 1337 if IS_LOGGING_YEARLY else 4

# Chart border and spacing settings
POS_SUBPLOT_TOP_EDGE = 0.920
POS_SUBPLOT_BOTTOM_EDGE = 0.067
POS_SUBPLOT_LEFT_EDGE = 0.055
POS_SUBPLOT_RIGHT_EDGE = 0.990
POS_SUBPLOT_HSPACE = 0.200
POS_SUBPLOT_WSPACE = 0.200

SHOW_LEGEND = False

STR_ALL_MOMENTS = "All moments"
STR_ALL_BUILDINGS = "All buildings"
STR_ALL_REGIONS = "All regions"
STR_ALL_GOODS = "All goods"
STR_ALL_ROAD_TYPES = "All road types"

ERROR_FILE_NOT_FOUND = f'{TARGET_FILE_NAME_ROOT}.log not found. Please set the log folder.'
ERROR_NO_DATA_MATCH = "No data matches the current filters"
ERROR_NO_STATISTICS = "The logs exist, but there are no statistics stored\nPlay more or get other logs"

# Percentile definition: (id, name, percentile_value, color)
PERCENTILE_SERIES = [
    ("max", "Maximum",               100, "#1b5e20"),  # Dark Green
    ("p99", "Extremely high (99th)",  99, "#2e7d32"),  # Forest Green
    ("p95", "Very high (95th)",       95, "#4caf50"),  # Green
    ("p75", "Above normal (75th)",    75, "#8bc34a"),  # Yellow-Green
    ("p50", "Normal (50th)",          50, "#fbc02d"),  # Gold / Yellow
    ("p25", "Below normal (25th)",    25, "#fb8c00"),  # Orange
    ("p05", "Very low (5th)",          5, "#f4511e"),  # Coral / Light Red
    ("p01", "Extremely low (1st)",     1, "#c62828"),  # Crimson
    ("min", "Minimum",                 0, "#b71c1c"),  # Dark Red
]
PERCENTILE_BY_ID = {entry[0]: entry for entry in PERCENTILE_SERIES}
STAT_COLORS = {entry[0]: entry[3] for entry in PERCENTILE_SERIES}

GRAPH_INTRODUCTION = """
Welcome to the M&T graphing tool!

Press '`' to see the list of available graphs.
Refresh (Ctrl+R) to read manually game.log again.

Open Settings [Ctrl+,] to adjust refresh and autosave frequencies.
"""