import csv
import os
import shutil

from src.parsing.computed_series import COMPUTED_SERIES_APPDATA_PATH, COMPUTED_SERIES_FILENAME, \
	DEFAULT_COMPUTED_SERIES_CSV, _reported_parsing_errors


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


def _show_parsing_error_dialog(err_msg: str, line_num: int):
    """Displays a warning dialog to the user if GUI is initialized."""
    err_key = (line_num, err_msg)
    if err_key in _reported_parsing_errors:
        return
    _reported_parsing_errors.add(err_key)

    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance():
            QMessageBox.critical(
                None,
                "Computed Series Parsing Error",
                f"Failed to parse formula in '{COMPUTED_SERIES_FILENAME}' on line {line_num}:\n\n{err_msg}"
            )
    except Exception:
        pass
