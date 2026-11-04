import copy
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QProgressBar,
    QPushButton, QComboBox, QLineEdit, QGroupBox, QMessageBox, QCheckBox,
    QSlider
)
from src.constants import APPDATA_DIR


def sort_hotkeys(keys):
    """Sorts hotkeys putting plain numbers (1..9, 0) first, followed by modifier combos."""
    def _sort_key(k):
        tokens = [t.strip() for t in k.split('+') if t.strip()]
        has_ctrl = any(t.lower() == 'ctrl' for t in tokens)
        has_alt = any(t.lower() == 'alt' for t in tokens)
        has_shift = any(t.lower() == 'shift' for t in tokens)
        base = [t for t in tokens if t.lower() not in ('ctrl', 'alt', 'shift')]
        base_str = base[0] if base else ""

        mod_score = (1 if has_ctrl else 0) * 1 + (2 if has_alt else 0) * 2 + (4 if has_shift else 0) * 4

        if base_str.isdigit():
            val = int(base_str)
            num_order = 10 if val == 0 else val
        elif base_str.startswith('F') and base_str[1:].isdigit():
            num_order = 100 + int(base_str[1:])
        else:
            num_order = 999

        return (mod_score, num_order, base_str)

    return sorted(keys, key=_sort_key)


class PresetConfigDialog(QDialog):
    """Dialog to view, add, edit, and assign preset values and hotkeys for chart filters."""
    def __init__(self, chart_title, filter_widget_map, key_configs, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Assign Preset Hotkeys - {chart_title}")
        self.resize(780, 540)

        self.chart_title = chart_title
        self.filter_widget_map = filter_widget_map
        self.key_configs = key_configs
        # Make a deep copy of existing presets for this chart so user can cancel safely
        self.presets = copy.deepcopy(key_configs.get(chart_title, {}))

        self.filter_combos = {}

        self._build_ui()
        self._populate_table()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        header = QLabel(f"<b>Configuring hotkey presets for chart:</b> {self.chart_title}")
        main_layout.addWidget(header)

        # Presets table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hotkey", "Description", "Filters"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        main_layout.addWidget(self.table)

        # Table buttons row (New / Delete)
        table_btn_layout = QHBoxLayout()
        self.btn_new = QPushButton("New Preset")
        self.btn_new.clicked.connect(self._on_new_preset)
        self.btn_delete = QPushButton("Delete Selected Preset")
        self.btn_delete.clicked.connect(self._on_delete_preset)
        table_btn_layout.addWidget(self.btn_new)
        table_btn_layout.addWidget(self.btn_delete)
        table_btn_layout.addStretch()
        main_layout.addLayout(table_btn_layout)

        # Preset editor groupbox
        form_group = QGroupBox("Preset Details")
        form_layout = QFormLayout(form_group)

        # Hotkey selector with Ctrl, Shift, Alt checkboxes + base key
        hotkey_layout = QHBoxLayout()
        self.chk_ctrl = QCheckBox("Ctrl")
        self.chk_shift = QCheckBox("Shift")
        self.chk_alt = QCheckBox("Alt")

        hotkey_layout.addWidget(self.chk_ctrl)
        hotkey_layout.addWidget(self.chk_shift)
        hotkey_layout.addWidget(self.chk_alt)

        self.combo_key = QComboBox()
        self.combo_key.setEditable(True)
        default_keys = [str(i) for i in range(1, 10)] + ["0"]
        self.combo_key.addItems(default_keys)
        self.combo_key.setFixedWidth(80)

        hotkey_layout.addWidget(QLabel("Key:"))
        hotkey_layout.addWidget(self.combo_key)
        hotkey_layout.addStretch()

        form_layout.addRow("Hotkey:", hotkey_layout)

        # Description
        self.edit_description = QLineEdit()
        self.edit_description.setPlaceholderText("e.g. Gravel Road / Britain")
        form_layout.addRow("Description:", self.edit_description)

        # Dropdowns for each filter in filter_widget_map
        for key, widget in self.filter_widget_map.items():
            if isinstance(widget, QComboBox):
                combo = QComboBox()
                combo.addItem("(Leave unchanged)")
                for i in range(widget.count()):
                    combo.addItem(widget.itemText(i))
                label_text = key.replace('_', ' ').title() + ":"
                form_layout.addRow(label_text, combo)
                self.filter_combos[key] = combo
                # Auto-update description when a selection is made
                combo.currentTextChanged.connect(self._on_filter_combo_changed)

        # Actions for the single preset
        preset_action_layout = QHBoxLayout()
        self.btn_capture = QPushButton("Capture Current Chart Values")
        self.btn_capture.setToolTip("Auto-fill description and dropdowns from the current chart filters.")
        self.btn_capture.clicked.connect(self._capture_current_chart_values)

        self.btn_save_preset = QPushButton("Save / Update Preset")
        self.btn_save_preset.setStyleSheet("font-weight: bold;")
        self.btn_save_preset.clicked.connect(self._save_single_preset)

        preset_action_layout.addWidget(self.btn_capture)
        preset_action_layout.addStretch()
        preset_action_layout.addWidget(self.btn_save_preset)
        form_layout.addRow(preset_action_layout)

        main_layout.addWidget(form_group)

        # Dialog buttons (Save & Close, Cancel)
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.btn_apply = QPushButton("Save and close")
        self.btn_apply.clicked.connect(self._on_apply_and_close)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        bottom_layout.addWidget(self.btn_apply)
        bottom_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(bottom_layout)

    def _on_filter_combo_changed(self, text):
        if not text or text == "(Leave unchanged)" or text.startswith("All "):
            return
        selected_parts = []
        for combo in self.filter_combos.values():
            val = combo.currentText()
            if val and val != "(Leave unchanged)" and not val.startswith("All "):
                selected_parts.append(val)
        if selected_parts:
            self.edit_description.setText(" - ".join(selected_parts))

    def _build_hotkey_string(self):
        parts = []
        if self.chk_ctrl.isChecked():
            parts.append("Ctrl")
        if self.chk_alt.isChecked():
            parts.append("Alt")
        if self.chk_shift.isChecked():
            parts.append("Shift")

        key = self.combo_key.currentText().strip()
        if not key:
            return ""
        parts.append(key)
        return "+".join(parts)

    def _set_hotkey_from_string(self, hotkey_str):
        tokens = [t.strip() for t in hotkey_str.split('+') if t.strip()]
        self.chk_ctrl.setChecked(any(t.lower() == 'ctrl' for t in tokens))
        self.chk_alt.setChecked(any(t.lower() == 'alt' for t in tokens))
        self.chk_shift.setChecked(any(t.lower() == 'shift' for t in tokens))

        non_modifiers = [t for t in tokens if t.lower() not in ('ctrl', 'alt', 'shift')]
        base_key = non_modifiers[0] if non_modifiers else ""

        idx = self.combo_key.findText(base_key)
        if idx != -1:
            self.combo_key.setCurrentIndex(idx)
        else:
            self.combo_key.setEditText(base_key)

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        sorted_keys = sort_hotkeys(self.presets.keys())
        for row, hotkey in enumerate(sorted_keys):
            cfg = self.presets[hotkey]
            desc = cfg.get("description", "")
            filters = cfg.get("filters", {})
            filter_str = ", ".join(f"{k}: {v}" for k, v in filters.items())

            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(hotkey))
            self.table.setItem(row, 1, QTableWidgetItem(desc))
            self.table.setItem(row, 2, QTableWidgetItem(filter_str))
        self.table.blockSignals(False)

    def _on_table_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        hotkey = self.table.item(row, 0).text()
        cfg = self.presets.get(hotkey, {})

        for combo in self.filter_combos.values():
            combo.blockSignals(True)

        self._set_hotkey_from_string(hotkey)
        self.edit_description.setText(cfg.get("description", ""))

        filters = cfg.get("filters", {})
        for key, combo in self.filter_combos.items():
            val = filters.get(key)
            if val is not None:
                c_idx = combo.findText(val)
                combo.setCurrentIndex(c_idx if c_idx != -1 else 0)
            else:
                combo.setCurrentIndex(0)

        for combo in self.filter_combos.values():
            combo.blockSignals(False)

    def _on_new_preset(self):
        self.table.clearSelection()
        self.chk_ctrl.setChecked(False)
        self.chk_alt.setChecked(False)
        self.chk_shift.setChecked(False)

        unused = None
        candidates = [str(i) for i in range(1, 10)] + ["0"]
        for c in candidates:
            if c not in self.presets:
                unused = c
                break

        if not unused:
            for c in candidates:
                cand = f"Ctrl+{c}"
                if cand not in self.presets:
                    unused = cand
                    break

        if not unused:
            unused = "1"

        self._set_hotkey_from_string(unused)
        self.edit_description.clear()
        for combo in self.filter_combos.values():
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)

    def _on_delete_preset(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Selection", "Please select a preset in the table to delete.")
            return
        row = selected_rows[0].row()
        hotkey = self.table.item(row, 0).text()
        if hotkey in self.presets:
            del self.presets[hotkey]
        self._populate_table()
        self._on_new_preset()

    def _capture_current_chart_values(self):
        desc_parts = []
        for key, combo in self.filter_combos.items():
            if key in self.filter_widget_map and isinstance(self.filter_widget_map[key], QComboBox):
                cur_text = self.filter_widget_map[key].currentText()
                c_idx = combo.findText(cur_text)
                if c_idx != -1:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(c_idx)
                    combo.blockSignals(False)
                    if not cur_text.startswith("All "):
                        desc_parts.append(cur_text)

        if desc_parts:
            self.edit_description.setText(" - ".join(desc_parts))

    def _save_single_preset(self):
        hotkey = self._build_hotkey_string()
        if not hotkey:
            QMessageBox.warning(self, "Invalid Hotkey", "Please enter or select a key (e.g. 1).")
            return

        desc = self.edit_description.text().strip()
        if not desc:
            desc = hotkey

        filters = {}
        for key, combo in self.filter_combos.items():
            if combo.currentIndex() > 0:
                filters[key] = combo.currentText()

        if not filters:
            QMessageBox.warning(self, "No Filters Set", "Please set at least one dropdown filter value for this preset.")
            return

        self.presets[hotkey] = {
            "description": desc,
            "filters": filters
        }
        self._populate_table()

        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == hotkey:
                self.table.selectRow(r)
                break

    def _on_apply_and_close(self):
        self.key_configs[self.chart_title] = self.presets
        self.accept()


class SettingsDialog(QDialog):
    """Settings modal dialog for configuring intervals, smoothing, and opening %appdata%."""
    def __init__(self, current_refresh_idx, current_autosave_idx, current_period, stats_shading_all=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(460, 300)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.combo_refresh = QComboBox()
        self.combo_refresh.addItems(["Refresh: 10s", "Refresh: 30s", "Refresh: 60s", "Refresh: 300s", "Refresh: 600s", "Refresh: Off"])
        self.combo_refresh.setCurrentIndex(current_refresh_idx)
        form_layout.addRow("Graph Refresh Interval:", self.combo_refresh)

        self.combo_autosave = QComboBox()
        self.combo_autosave.addItems(["Auto-save: 1m", "Auto-save: 5m", "Auto-save: 10m", "No auto-save"])
        self.combo_autosave.setCurrentIndex(current_autosave_idx)
        form_layout.addRow("Session Auto-Save Interval:", self.combo_autosave)

        slider_layout = QHBoxLayout()
        self.slider_period = QSlider(Qt.Orientation.Horizontal)
        self.slider_period.setRange(2, 50)
        self.slider_period.setValue(current_period)
        self.lbl_period = QLabel(str(current_period))
        self.slider_period.valueChanged.connect(lambda v: self.lbl_period.setText(str(v)))
        slider_layout.addWidget(self.slider_period)
        slider_layout.addWidget(self.lbl_period)
        form_layout.addRow("Moving Average Period:", slider_layout)

        # Percentile Shading Mode toggle
        self.chk_stats_shading_all = QCheckBox("Shade all percentile bands (Yellow IQR, redder high, greener low)")
        self.chk_stats_shading_all.setToolTip("When checked, colors all percentile spaces. When unchecked, only shades the IQR band.")
        self.chk_stats_shading_all.setChecked(stats_shading_all)
        form_layout.addRow("Percentile Shading:", self.chk_stats_shading_all)

        layout.addLayout(form_layout)

        btn_appdata = QPushButton("Open AppData Folder")
        btn_appdata.clicked.connect(self._open_appdata)
        layout.addWidget(btn_appdata)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _open_appdata(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(APPDATA_DIR))

    def get_settings(self):
        return {
            "refresh_idx": self.combo_refresh.currentIndex(),
            "autosave_idx": self.combo_autosave.currentIndex(),
            "period": self.slider_period.value(),
            "stats_shading_all": self.chk_stats_shading_all.isChecked()
        }


class ChartSelectionDialog(QDialog):
    """Modal dialog displaying available charts with assigned hotkeys."""
    def __init__(self, graphs_dict, hotkey_target_dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select a Chart")
        self.graphs = graphs_dict
        self.hotkey_target_dict = hotkey_target_dict
        self.selected_chart = None

        self.layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Chart Name", "Hotkey"])
        self.table.setRowCount(len(self.graphs))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self._populate_table()

        self.layout.addWidget(self.table)
        self.table.cellDoubleClicked.connect(self.on_double_click)
        self.table.activated.connect(self.on_activated)

    def _populate_table(self):
        sorted_charts = sorted(self.graphs.keys())
        for i, chart_name in enumerate(sorted_charts):
            hotkey = f"F{i + 1}"
            self.hotkey_target_dict[hotkey] = chart_name
            self.table.setItem(i, 0, QTableWidgetItem(chart_name))
            self.table.setItem(i, 1, QTableWidgetItem(hotkey))

    def on_double_click(self, row, column):
        self.accept_selection(row)

    def on_activated(self, index):
        self.accept_selection(index.row())

    def accept_selection(self, row):
        self.selected_chart = self.table.item(row, 0).text()
        self.accept()


class LoadingDialog(QDialog):
    """Frameless indeterminate loading indicator dialog."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Loading Application")
        self.setFixedSize(350, 120)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.label = QLabel("Loading log files, please wait...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.label.font()
        font.setPointSize(10)
        self.label.setFont(font)
        layout.addWidget(self.label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)


class FilterSearchDialog(QDialog):
    """Search dialog to find entries across all comboboxes of the current chart (Ctrl+F)."""
    def __init__(self, filter_widget_map, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find Filter / Metric")
        self.resize(600, 800)
        self.filter_widget_map = filter_widget_map
        self.selected_target = None  # Tuple of (target_combo, item_text)

        layout = QVBoxLayout(self)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter options across all dropdowns...")
        search_layout.addWidget(self.search_edit)
        layout.addLayout(search_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Dropdown", "Value"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_select = QPushButton("Select")
        self.btn_select.clicked.connect(self._accept_current)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_select)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        # Build list of all items across dropdowns
        self.all_entries = []
        time_entries = []
        for key, widget in self.filter_widget_map.items():
            if isinstance(widget, QComboBox):
                combo_name = key.replace('_', ' ').title()
                is_moment = (key == 'moment')
                for i in range(widget.count()):
                    val_str = widget.itemText(i)
                    target_list = time_entries if is_moment else self.all_entries
                    target_list.append((widget, combo_name, val_str))

        # Append all time/year items to the end
        self.all_entries.extend(time_entries)

        self.search_edit.textChanged.connect(self._populate_results)
        self.table.itemDoubleClicked.connect(lambda: self._accept_current())
        self._populate_results("")
        self.search_edit.setFocus()

    def _populate_results(self, filter_text):
        query = filter_text.strip().lower()
        matched = [e for e in self.all_entries if query in e[2].lower() or query in e[1].lower()]

        self.table.setRowCount(len(matched))
        self.current_matched = matched
        for row, (_, category, val_str) in enumerate(matched):
            self.table.setItem(row, 0, QTableWidgetItem(category))
            self.table.setItem(row, 1, QTableWidgetItem(val_str))
        if matched:
            self.table.selectRow(0)

    def _accept_current(self):
        sel = self.table.selectionModel().selectedRows()
        if sel and sel[0].row() < len(self.current_matched):
            combo, _, val_str = self.current_matched[sel[0].row()]
            self.selected_target = (combo, val_str)
            self.accept()
        else:
            self.reject()