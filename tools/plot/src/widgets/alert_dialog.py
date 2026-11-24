import uuid
from PyQt6.QtCore import Qt, QStringListModel
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QHeaderView,
    QPushButton, QComboBox, QLineEdit, QCheckBox, QGroupBox, QFormLayout,
    QTableWidgetItem, QSplitter, QWidget, QSizePolicy, QCompleter
)

from src.services.alert_manager import load_alerts, save_alerts, evaluate_alert_rule
from src.widgets.formula_completer import FormulaLineEdit
import src.parsing.stores as stores


class AlertDialog(QDialog):
    """Alert Management dialog for configuring rules and testing boolean conditions live."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alert Rules & Monitoring Configuration")
        self.resize(1120, 720)

        self.rules = load_alerts()
        self.current_rule_idx = -1
        self.main_window = parent

        self._build_ui()
        self._populate_table()
        if self.rules:
            self.table.selectRow(0)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        header = QLabel(
            "<h3>Alert Rules Configuration</h3>"
            "Configure alerts using boolean criteria and transformation functions: "
            "<code>rate(X)</code>, <code>relative_rate(X)</code>, <code>acceleration(X)</code>, "
            "<code>ratio(X)</code>, <code>difference(X)</code>, <code>density_by_location(X)</code>, <code>density_by_population(X)</code>"
        )
        main_layout.addWidget(header)

        # Global Master Toggles Row
        global_controls_row = QHBoxLayout()
        self.chk_global_alerts = QCheckBox("Enable Alerts Monitoring [Alt+A]")
        self.chk_global_alerts.setChecked(getattr(self.main_window, 'alerts_enabled', True))
        self.chk_global_alerts.toggled.connect(self._on_toggle_global_alerts)

        self.chk_global_sounds = QCheckBox("Enable Alert Sounds [Alt+S]")
        self.chk_global_sounds.setChecked(getattr(self.main_window, 'alert_sounds_enabled', True))
        self.chk_global_sounds.toggled.connect(self._on_toggle_global_sounds)

        global_controls_row.addWidget(self.chk_global_alerts)
        global_controls_row.addWidget(self.chk_global_sounds)
        global_controls_row.addStretch()

        self.btn_disable_all = QPushButton("Turn Off All Alerts [Alt+D]")
        self.btn_disable_all.clicked.connect(self._turn_off_all_alerts)
        self.btn_enable_all = QPushButton("Turn On All Alerts [Alt+E]")
        self.btn_enable_all.clicked.connect(self._turn_on_all_alerts)

        global_controls_row.addWidget(self.btn_disable_all)
        global_controls_row.addWidget(self.btn_enable_all)
        main_layout.addLayout(global_controls_row)

        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter, stretch=1)

        # Upper Table: Rules List
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Active", "Alert Name", "Dataset", "Entity Filter", "Condition"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_rule_selected)
        top_layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("New Alert")
        self.btn_new.clicked.connect(self._on_new_rule)
        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.clicked.connect(self._on_delete_rule)
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch()
        top_layout.addLayout(btn_row)

        splitter.addWidget(top_widget)

        # Lower Form: Editor and Test Panel
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        editor_group = QGroupBox("Edit Alert Rule")
        form_layout = QFormLayout(editor_group)

        # Name and Dataset
        row1 = QHBoxLayout()
        self.edit_name = QLineEdit()
        self.combo_dataset = QComboBox()
        self.combo_dataset.addItems(["country", "market", "region"])
        self.combo_dataset.currentIndexChanged.connect(self._on_dataset_changed)

        self.edit_entity = QLineEdit("All")
        self.entity_completer = QCompleter(self)
        self.entity_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.edit_entity.setCompleter(self.entity_completer)

        row1.addWidget(QLabel("Name:"))
        row1.addWidget(self.edit_name, stretch=2)
        row1.addWidget(QLabel("Dataset:"))
        row1.addWidget(self.combo_dataset, stretch=1)
        row1.addWidget(QLabel("Entity:"))
        row1.addWidget(self.edit_entity, stretch=1)
        form_layout.addRow(row1)

        # Autocompleting Condition Expression
        self.edit_condition = FormulaLineEdit(dataset_type="country")
        self.edit_condition.setPlaceholderText("e.g. rate(total_debt) > 24 and density_by_population([Unemployed peasants]) > 0.7")
        self.edit_condition.setFont(QFont("Consolas", 10))
        form_layout.addRow("Condition:", self.edit_condition)

        self._update_entity_completer("country")

        row2 = QHBoxLayout()
        self.chk_enabled = QCheckBox("Rule Enabled")
        self.chk_enabled.setChecked(True)
        row2.addWidget(self.chk_enabled)
        row2.addStretch()

        self.btn_test = QPushButton("Test Condition")
        self.btn_test.setStyleSheet("font-weight: bold; background-color: #2b5797; color: white; padding: 6px 14px;")
        self.btn_test.clicked.connect(self._on_test_condition)

        self.btn_update = QPushButton("Save Rule Changes")
        self.btn_update.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_update.clicked.connect(self._on_save_rule_changes)

        row2.addWidget(self.btn_test)
        row2.addWidget(self.btn_update)
        form_layout.addRow(row2)

        bottom_layout.addWidget(editor_group)

        # Test Result Status Label
        self.lbl_test_result = QLabel("Click 'Test Condition' to check if the condition fires against loaded data.")
        self.lbl_test_result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lbl_test_result.setFixedHeight(40)
        self.lbl_test_result.setStyleSheet(
            "padding: 8px; border-radius: 4px; background-color: #2e2e2e; color: #dcdcdc; font-weight: bold;"
        )
        bottom_layout.addWidget(self.lbl_test_result)

        # Matches Preview Table
        self.table_matches = QTableWidget()
        self.table_matches.setColumnCount(4)
        self.table_matches.setHorizontalHeaderLabels(["Year", "Entity", "Condition", "Values"])
        self.table_matches.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_matches.verticalHeader().setVisible(False)
        self.table_matches.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_matches.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_matches.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_matches.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_matches.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        bottom_layout.addWidget(self.table_matches, stretch=1)

        splitter.addWidget(bottom_widget)

        # Bottom Dialog Actions
        bottom_dialog_row = QHBoxLayout()
        bottom_dialog_row.addStretch()
        self.btn_apply = QPushButton("Save and Close")
        self.btn_apply.setStyleSheet("font-weight: bold; padding: 6px 18px;")
        self.btn_apply.clicked.connect(self._on_apply_and_close)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_dialog_row.addWidget(self.btn_apply)
        bottom_dialog_row.addWidget(self.btn_cancel)
        main_layout.addLayout(bottom_dialog_row)

        self._setup_dialog_shortcuts()

    def _setup_dialog_shortcuts(self):
        QShortcut(QKeySequence("Alt+D"), self).activated.connect(self._turn_off_all_alerts)
        QShortcut(QKeySequence("Alt+E"), self).activated.connect(self._turn_on_all_alerts)
        QShortcut(QKeySequence("Alt+A"), self).activated.connect(self.chk_global_alerts.toggle)
        QShortcut(QKeySequence("Alt+S"), self).activated.connect(self.chk_global_sounds.toggle)

    def _on_toggle_global_alerts(self, checked):
        if self.main_window:
            self.main_window.alerts_enabled = checked
            self.main_window.save_app_settings()

    def _on_toggle_global_sounds(self, checked):
        if self.main_window:
            self.main_window.alert_sounds_enabled = checked
            self.main_window.save_app_settings()

    def _turn_off_all_alerts(self):
        for r in self.rules:
            r["enabled"] = False
        self.chk_enabled.setChecked(False)
        self._populate_table()

    def _turn_on_all_alerts(self):
        for r in self.rules:
            r["enabled"] = True
        self.chk_enabled.setChecked(True)
        self._populate_table()

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row, r in enumerate(self.rules):
            self.table.insertRow(row)
            active_str = "✓" if r.get("enabled", True) else " "
            self.table.setItem(row, 0, QTableWidgetItem(active_str))
            self.table.setItem(row, 1, QTableWidgetItem(r.get("name", "Unnamed")))
            self.table.setItem(row, 2, QTableWidgetItem(r.get("dataset_type", "country")))
            self.table.setItem(row, 3, QTableWidgetItem(r.get("entity_filter", "All")))
            self.table.setItem(row, 4, QTableWidgetItem(r.get("condition", "")))
        self.table.blockSignals(False)

    def _on_rule_selected(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        idx = sel[0].row()
        if 0 <= idx < len(self.rules):
            self.current_rule_idx = idx
            r = self.rules[idx]
            d_type = r.get("dataset_type", "country")
            self.edit_name.setText(r.get("name", ""))
            self.combo_dataset.blockSignals(True)
            self.combo_dataset.setCurrentText(d_type)
            self.combo_dataset.blockSignals(False)
            self.edit_condition.set_dataset_type(d_type)
            self._update_entity_completer(d_type)
            self.edit_entity.setText(r.get("entity_filter", "All"))
            self.edit_condition.setText(r.get("condition", ""))
            self.chk_enabled.setChecked(r.get("enabled", True))
            self.lbl_test_result.setStyleSheet(
                "padding: 8px; border-radius: 4px; background-color: #2e2e2e; color: #dcdcdc; font-weight: bold;"
            )
            self.lbl_test_result.setText("Rule selected. Click 'Test Condition' to evaluate.")
            self.table_matches.setRowCount(0)

    def _collect_current_rule(self):
        r_id = self.rules[self.current_rule_idx].get("id") if (0 <= self.current_rule_idx < len(self.rules)) else str(uuid.uuid4())
        return {
            "id": r_id,
            "name": self.edit_name.text().strip() or "Unnamed Alert",
            "dataset_type": self.combo_dataset.currentText(),
            "entity_filter": self.edit_entity.text().strip() or "All",
            "condition": self.edit_condition.text().strip(),
            "enabled": self.chk_enabled.isChecked(),
        }

    def _on_new_rule(self):
        new_rule = {
            "id": str(uuid.uuid4()),
            "name": "New Alert",
            "dataset_type": "country",
            "entity_filter": "All",
            "condition": "rate(total_debt) > 100",
            "enabled": True
        }
        self.rules.append(new_rule)
        self._populate_table()
        self.table.selectRow(len(self.rules) - 1)

    def _on_delete_rule(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        idx = sel[0].row()
        del self.rules[idx]
        self._populate_table()
        if self.rules:
            self.table.selectRow(max(0, idx - 1))
        else:
            self.current_rule_idx = -1

    def _on_save_rule_changes(self):
        if self.current_rule_idx < 0 or self.current_rule_idx >= len(self.rules):
            return
        self.rules[self.current_rule_idx] = self._collect_current_rule()
        self._populate_table()
        self.table.selectRow(self.current_rule_idx)

    def _on_test_condition(self):
        """Tests the current condition live, with Green/Red result highlighting."""
        temp_rule = self._collect_current_rule()
        status, matches, err_msg = evaluate_alert_rule(temp_rule, latest_only=False)

        self.table_matches.setRowCount(0)

        if status == "FIRED":
            self.lbl_test_result.setStyleSheet(
                "padding: 8px; border-radius: 4px; background-color: #1e4620; color: #7cfc00; font-weight: bold; border: 1px solid #4caf50;"
            )
            most_recent = matches[0]
            self.lbl_test_result.setText(
                f"✓ CONDITION FIRED! Triggered {len(matches)} time(s). Most recent: {most_recent['entity']} at Year {most_recent['moment']}."
            )
            for row, m in enumerate(matches[:50]):
                val_str = str(m.get("values", ""))
                val_item = QTableWidgetItem(val_str)
                val_item.setToolTip(val_str)

                self.table_matches.insertRow(row)
                self.table_matches.setItem(row, 0, QTableWidgetItem(str(m["moment"])))
                self.table_matches.setItem(row, 1, QTableWidgetItem(m["entity"]))
                self.table_matches.setItem(row, 2, QTableWidgetItem(m["condition"]))
                self.table_matches.setItem(row, 3, val_item)

        elif status == "NOT_FIRED":
            self.lbl_test_result.setStyleSheet(
                "padding: 8px; border-radius: 4px; background-color: #4a1c1a; color: #ff6b6b; font-weight: bold; border: 1px solid #f44336;"
            )
            self.lbl_test_result.setText("✗ CONDITION NOT FIRED. Criteria not satisfied in any loaded record.")

        else:
            self.lbl_test_result.setStyleSheet(
                "padding: 8px; border-radius: 4px; background-color: #3b0000; color: #ff9999; font-weight: bold; border: 1px solid #d32f2f;"
            )
            self.lbl_test_result.setText(f"⚠ ERROR: {err_msg}")

    def _on_apply_and_close(self):
        if 0 <= self.current_rule_idx < len(self.rules):
            self.rules[self.current_rule_idx] = self._collect_current_rule()
        save_alerts(self.rules)
        self.accept()

    def _on_dataset_changed(self):
        d_type = self.combo_dataset.currentText()
        self.edit_condition.set_dataset_type(d_type)
        self._update_entity_completer(d_type)

    def _update_entity_completer(self, d_type):
        entities = {"All"}
        if d_type == "country":
            for r in stores.tg_cumulative_store.values():
                if r.get("tag"): entities.add(r["tag"])
                if r.get("name"): entities.add(r["name"])
        elif d_type == "market":
            for k in stores.mk_cumulative_store.keys():
                entities.add(k[1])
        elif d_type == "region":
            entities.update(stores.region_locations_store.keys())
            for k in stores.pop_cumulative_store.keys():
                entities.add(k[1])

        self.entity_completer.setModel(QStringListModel(sorted(entities), self.entity_completer))