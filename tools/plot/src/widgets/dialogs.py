import copy
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QProgressBar,
    QPushButton, QComboBox, QLineEdit, QGroupBox, QMessageBox
)

class PresetConfigDialog(QDialog):
    """Dialog to view, add, edit, and assign preset values and hotkeys for chart filters."""
    def __init__(self, chart_title, filter_widget_map, key_configs, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Assign Preset Hotkeys - {chart_title}")
        self.resize(750, 520)

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

        # Hotkey selector
        self.combo_hotkey = QComboBox()
        self.combo_hotkey.setEditable(True)
        default_hotkeys = [f"F{i}" for i in range(1, 13)]
        self.combo_hotkey.addItems(default_hotkeys)
        form_layout.addRow("Hotkey:", self.combo_hotkey)

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

    def _sort_hotkeys(self, keys):
        def _sort_key(k):
            if k.startswith('F') and k[1:].isdigit():
                return (0, int(k[1:]))
            return (1, k)
        return sorted(keys, key=_sort_key)

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        sorted_keys = self._sort_hotkeys(self.presets.keys())
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

        idx = self.combo_hotkey.findText(hotkey)
        if idx != -1:
            self.combo_hotkey.setCurrentIndex(idx)
        else:
            self.combo_hotkey.setEditText(hotkey)

        self.edit_description.setText(cfg.get("description", ""))

        filters = cfg.get("filters", {})
        for key, combo in self.filter_combos.items():
            val = filters.get(key)
            if val is not None:
                c_idx = combo.findText(val)
                combo.setCurrentIndex(c_idx if c_idx != -1 else 0)
            else:
                combo.setCurrentIndex(0)

    def _on_new_preset(self):
        self.table.clearSelection()
        unused = "F1"
        for i in range(1, 13):
            candidate = f"F{i}"
            if candidate not in self.presets:
                unused = candidate
                break

        idx = self.combo_hotkey.findText(unused)
        if idx != -1:
            self.combo_hotkey.setCurrentIndex(idx)
        else:
            self.combo_hotkey.setEditText(unused)

        self.edit_description.clear()
        for combo in self.filter_combos.values():
            combo.setCurrentIndex(0)

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
                    combo.setCurrentIndex(c_idx)
                    if not cur_text.startswith("All "):
                        desc_parts.append(cur_text)

        if not self.edit_description.text() and desc_parts:
            self.edit_description.setText(" - ".join(desc_parts))

    def _save_single_preset(self):
        hotkey = self.combo_hotkey.currentText().strip()
        if not hotkey:
            QMessageBox.warning(self, "Invalid Hotkey", "Please enter or select a hotkey (e.g. F1).")
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
            hotkey = str(i + 1)
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