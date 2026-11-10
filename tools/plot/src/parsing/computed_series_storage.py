import csv
import os
import shutil

from src.constants import APPDATA_DIR

COMPUTED_SERIES_FILENAME = "computed_series.csv"
COMPUTED_SERIES_APPDATA_PATH = os.path.join(APPDATA_DIR, COMPUTED_SERIES_FILENAME)

DEFAULT_COMPUTED_SERIES_CSV = """dataset_type,new_metric_name,expression,description
country,Debt/Income,total_debt / income,Total debt divided by annual/monthly income
country,Adjusted Burden,[Debt/Income] * bank_interest,Interest payment burden
country,Credit Supply/Demand,Supply / Demand,Credit supply to demand ratio
region,Gold/Gold Mine,Gold / gold_mine,Gold price divided by gold mines
region,Food net,[Food production] + [Food consumption],Remaining produced food
market,Estate/state trade capacity,[Burgher Trade Capacity] / [Merchant Capacity],
"""

_reported_parsing_errors = set()
_parsing_error_callback = None

def set_parsing_error_callback(cb):
    """Allows UI to hook into formula parsing errors without coupling this module to PyQt6."""
    global _parsing_error_callback
    _parsing_error_callback = cb

def notify_parsing_error(err_msg: str, line_num: int):
    err_key = (line_num, err_msg)
    if err_key in _reported_parsing_errors:
        return
    _reported_parsing_errors.add(err_key)
    print(f"[COMPUTED SERIES ERROR] Line {line_num}: {err_msg}")
    if _parsing_error_callback:
        _parsing_error_callback(err_msg, line_num)

def ensure_computed_series_file():
    """Initializes computed_series.csv in APPDATA if not already present."""
    if not os.path.exists(COMPUTED_SERIES_APPDATA_PATH):
        if os.path.exists(COMPUTED_SERIES_FILENAME):
            shutil.copy(COMPUTED_SERIES_FILENAME, COMPUTED_SERIES_APPDATA_PATH)
        else:
            with open(COMPUTED_SERIES_APPDATA_PATH, "w", encoding="utf-8") as f:
                f.write(DEFAULT_COMPUTED_SERIES_CSV)

def load_raw_computed_series_rows():
    """Loads all formula rows as raw dictionaries for UI editing."""
    ensure_computed_series_file()
    filepath = COMPUTED_SERIES_APPDATA_PATH if os.path.exists(COMPUTED_SERIES_APPDATA_PATH) else COMPUTED_SERIES_FILENAME
    rows = []
    if not os.path.exists(filepath):
        return rows
    try:
        with open(filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append({
                    "dataset_type": r.get("dataset_type", "").strip().lower(),
                    "new_metric_name": r.get("new_metric_name", "").strip(),
                    "expression": r.get("expression", "").strip(),
                    "description": r.get("description", "").strip(),
                })
    except Exception as e:
        print(f"Error loading computed series rows: {e}")
    return rows

def save_computed_series_rows(rows):
    """Writes formula rows back to computed_series.csv in APPDATA."""
    ensure_computed_series_file()
    filepath = COMPUTED_SERIES_APPDATA_PATH
    with open(filepath, mode="w", encoding="utf-8", newline="") as f:
        fieldnames = ["dataset_type", "new_metric_name", "expression", "description"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "dataset_type": r.get("dataset_type", "").strip().lower(),
                "new_metric_name": r.get("new_metric_name", "").strip(),
                "expression": r.get("expression", "").strip(),
                "description": r.get("description", "").strip(),
            })