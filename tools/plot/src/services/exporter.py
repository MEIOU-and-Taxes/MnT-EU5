import csv
import os

import numpy as np
import pandas as pd
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication

from src.parsing.transformers.country import parse_data_countries, parse_data_credit_raw
from src.parsing.transformers.region import parse_data_building_types, parse_data_road_types, \
    parse_data_population, parse_data_goods_prices
from src.parsing.transformers.market import parse_data_markets

PARSERS = {
    "building_types": parse_data_building_types,
    "goods_prices": parse_data_goods_prices,
    "markets": parse_data_markets,
    "population": parse_data_population,
    "road_types": parse_data_road_types,
    "country_stats": parse_data_countries,
    "credit_stats": parse_data_credit_raw,
}

def check_file_locks(export_folder_path, filenames):
    to_check = list(filenames)
    if "country_stats" in to_check:
        to_check.append("country_stats_cleaned")

    for name in to_check:
        full_path = os.path.join(export_folder_path, f"{name}.csv")
        if os.path.exists(full_path):
            try:
                with open(full_path, 'a'):
                    pass
            except (IOError, PermissionError):
                return full_path
    return None

def load_location_data(filepath="locations.csv"):
    loc_map = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, mode='r', encoding='utf-8') as infile:
                for row in csv.DictReader(infile):
                    area = row.get('area')
                    if area:
                        loc_map[area] = {
                            'continent': row.get('continent', 'N/A'),
                            'subcontinent': row.get('subcontinent', 'N/A'),
                            'region': row.get('region', 'N/A')
                        }
        except Exception:
            pass
    return loc_map

def run_export_pipeline(data: str, log_folder: str, parent_widget=None) -> bool:
    if not data:
        QMessageBox.warning(parent_widget, "Export Error", "No log data loaded. Please refresh first.")
        return False

    export_path = os.path.join(log_folder, "csv_export")
    locked = check_file_locks(export_path, list(PARSERS.keys()))
    if locked:
        QMessageBox.critical(parent_widget, "File In Use", f"Please close the file and try again:\n\n{locked}")
        return False

    location_lookup = load_location_data()
    progress = QProgressDialog("Preparing export...", "Cancel", 0, len(PARSERS), parent_widget)
    progress.setWindowTitle("Export Progress")
    progress.resize(600, 140)
    progress.show()
    QApplication.processEvents()

    os.makedirs(export_path, exist_ok=True)
    exported_files = []

    try:
        for idx, (root_name, parser) in enumerate(PARSERS.items()):
            progress.setValue(idx)
            progress.setLabelText(f"Exporting {root_name}...")
            QApplication.processEvents()

            if progress.wasCanceled():
                return False

            dataset = parser(data)
            if not dataset:
                continue

            if root_name == "country_stats" and location_lookup:
                dataset_to_write = []
                for rec in dataset:
                    geo = location_lookup.get(rec.get('capital_area'), {})
                    enhanced = {'continent': geo.get('continent', 'N/A'),
                                'subcontinent': geo.get('subcontinent', 'N/A'),
                                'region': geo.get('region', 'N/A')}
                    enhanced.update(rec)
                    dataset_to_write.append(enhanced)
            else:
                dataset_to_write = dataset

            target_file = os.path.join(export_path, f"{root_name}.csv")
            with open(target_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=dataset_to_write[0].keys())
                writer.writeheader()
                writer.writerows(dataset_to_write)
            exported_files.append(target_file)

            if root_name == "country_stats" and dataset_to_write:
                df = pd.DataFrame(dataset_to_write)
                if 'num_locations' in df.columns:
                    df_cleaned = df[df['num_locations'] > 0].copy()
                    for est in ['nobles', 'clergy', 'burghers', 'peasants', 'dhimmi', 'tribes', 'cossacks']:
                        col = f'{est}_relative_power'
                        if col in df_cleaned.columns:
                            mask = df_cleaned[col] == 0
                            stats_cols = [c for c in df_cleaned.columns if c.startswith(f'{est}_')]
                            df_cleaned.loc[mask, stats_cols] = np.nan
                    clean_path = os.path.join(export_path, "country_stats_cleaned.csv")
                    df_cleaned.to_csv(clean_path, index=False)
                    exported_files.append(clean_path)

        progress.setValue(len(PARSERS))

        msg = QMessageBox(parent_widget)
        msg.setWindowTitle("Export Successful")
        msg.setText(f"Exported files to:\n{export_path}")
        btn_open = msg.addButton("Open Directory", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Ok)
        msg.exec()
        if msg.clickedButton() == btn_open:
            QDesktopServices.openUrl(QUrl.fromLocalFile(export_path))
        return True

    except Exception as e:
        progress.close()
        QMessageBox.critical(parent_widget, "Export Failed", f"Export error: {e}")
        return False