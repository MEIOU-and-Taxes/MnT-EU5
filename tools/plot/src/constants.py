import os

APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'MnT_Plotter')
os.makedirs(APPDATA_DIR, exist_ok=True)

KEY_CONFIGS_PATH = os.path.join(APPDATA_DIR, "key_configs.json")
SETTINGS_PATH = os.path.join(APPDATA_DIR, "settings.json")
AUTOSAVE_DIR = os.path.join(APPDATA_DIR, "autosaves")
os.makedirs(AUTOSAVE_DIR, exist_ok=True)

FILE_CHECK_PERIOD_MS = 5 * 1000
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

# Statistical Mode Color Scheme
STAT_COLORS = {
    "Maximum": "#1b5e20",               # Dark Green
    "Extremely high (99th)": "#2e7d32",  # Forest Green
    "Very high (95th)": "#4caf50",       # Green
    "Above normal (75th)": "#8bc34a",    # Yellow-Green
    "Normal (50th)": "#fbc02d",          # Gold / Yellow
    "Below normal (25th)": "#fb8c00",    # Orange
    "Very low (5th)": "#f4511e",         # Coral / Light Red
    "Extremely low (1st)": "#c62828",    # Crimson
    "Minimum": "#b71c1c",                # Dark Red
}

GRAPH_INTRODUCTION = """
Welcome to the M&T graphing tool!

Press '`' to see the list of available graphs.
Refresh (Ctrl+R) to read manually game.log again.

Open Settings [Ctrl+,] to adjust refresh and autosave frequencies.
"""