import uuid
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QHeaderView,
    QPushButton, QComboBox, QLineEdit, QCheckBox, QGroupBox, QFormLayout,
    QTableWidgetItem, QMessageBox, QSplitter, QWidget
)

from src.services.alert_manager import load_alerts, save_alerts, evaluate_alert_rule


class AlertDialog(QDialog):
    """Alert Management dialog with live test highlighting and transformation options."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alert Rules and Monitoring")
        self.resize(1120, 700)

        self.rules = load_alerts()
        self.current_rule_idx = -1

        self._build_ui()
        self._populate_table()
        if self.rules:
            self.table.selectRow(0)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        header = QLabel("<h3>Alert Rules & Trigger Conditions</h3>Configure automated alerts with complex boolean criteria and test them live.")
        main_layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter, stretch=1)

        # Upper Table: Rules List
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Active", "Alert Name", "Dataset", "Entity Filter", "Density", "Baseline", "Order", "Condition"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
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
        self.edit_entity = QLineEdit("All")
        self.edit_entity.setPlaceholderText("All, or specific tag (e.g. FRA, London)")
        row1.addWidget(QLabel("Name:"))
        row1.addWidget(self.edit_name, stretch=2)
        row1.addWidget(QLabel("Dataset:"))
        row1.addWidget(self.combo_dataset, stretch=1)
        row1.addWidget(QLabel("Entity:"))
        row1.addWidget(self.edit_entity, stretch=1)
        form_layout.addRow(row1)

        # Condition Expression
        self.edit_condition = QLineEdit()
        self.edit_condition.setPlaceholderText("e.g. [Total Population] < 45000000 and [Average literacy] < 0.2")
        self.edit_condition.setFont(QFont("Consolas", 10))
        form_layout.addRow("Condition (AND/OR/NOT):", self.edit_condition)

        # Transformations: Density, Baseline, Derivative
        row2 = QHBoxLayout()
        self.combo_density = QComboBox()
        self.combo_density.addItems(["none", "location", "population"])
        self.combo_baseline = QComboBox()
        self.combo_baseline.addItems(["none", "ratio", "difference"])
        self.combo_derivative = QComboBox()
        self.combo_derivative.addItems(["0 (Base)", "1 (Rate Δ)", "2 (Acceleration Δ²)"])

        row2.addWidget(QLabel("Density Mode:"))
        row2.addWidget(self.combo_density)
        row2.addWidget(QLabel("Baseline Mode:"))
        row2.addWidget(self.combo_baseline)
        row2.addWidget(QLabel("Derivative:"))
        row2.addWidget(self.combo_derivative)
        row2.addStretch()
        form_layout.addRow(row2)

        # Notification toggles and active state
        row3 = QHBoxLayout()
        self.chk_enabled = QCheckBox("Rule Enabled")
        self.chk_enabled.setChecked(True)
        self.chk_popup = QCheckBox("Show Popup Dialog")
        self.chk_popup.setChecked(True)
        self.chk_sound = QCheckBox("Play Sound / Beep")
        self.chk_sound.setChecked(True)
        row3.addWidget(self.chk_enabled)
        row3.addWidget(self.chk_popup)
        row3.addWidget(self.chk_sound)
        row3.addStretch()
        form_layout.addRow(row3)

        # Test and Save buttons
        action_row = QHBoxLayout()
        self.btn_test = QPushButton("Test Condition")
        self.btn_test.setStyleSheet("font-weight: bold; background-color: #2b5797; color: white; padding: 6px 14px;")
        self.btn_test.clicked.connect(self._on_test_condition)

        self.btn_update = QPushButton("Save Rule Changes")
        self.btn_update.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_update.clicked.connect(self._on_save_rule_changes)

        action_row.addWidget(self.btn_test)
        action_row.addStretch()
        action_row.addWidget(self.btn_update)
        form_layout.addRow(action_row)

        bottom_layout.addWidget(editor_group)

        # Live Test Result Indicator
        self.lbl_test_result = QLabel("Click 'Test Condition' to check if the condition fires against loaded data.")
        self.lbl_test_result.setStyleSheet("padding: 8px; border-radius: 4px; background-color: #2e2e2e; color: #dcdcdc; font-weight: bold;")
        bottom_layout.addWidget(self.lbl_test_result)

        # Matches Preview Table
        self.table_matches = QTableWidget()
        self.table_matches.setColumnCount(3)
        self.table_matches.setHorizontalHeaderLabels(["Moment / Year", "Entity", "Condition Fired"])
        self.table_matches.verticalHeader().setVisible(False)
        self.table_matches.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_matches.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_matches.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_matches.setFixedHeight(120)
        bottom_layout.addWidget(self.table_matches)

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
            self.table.setItem(row, 4, QTableWidgetItem(r.get("density_mode", "none")))
            self.table.setItem(row, 5, QTableWidgetItem(r.get("baseline_mode", "none")))
            self.table.setItem(row, 6, QTableWidgetItem(str(r.get("derivative_order", 0))))
            self.table.setItem(row, 7, QTableWidgetItem(r.get("condition", "")))
        self.table.blockSignals(False)

    def _on_rule_selected(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        idx = sel[0].row()
        if 0 <= idx < len(self.rules):
            self.current_rule_idx = idx
            r = self.rules[idx]
            self.edit_name.setText(r.get("name", ""))
            self.combo_dataset.setCurrentText(r.get("dataset_type", "country"))
            self.edit_entity.setText(r.get("entity_filter", "All"))
            self.edit_condition.setText(r.get("condition", ""))
            self.combo_density.setCurrentText(r.get("density_mode", "none"))
            self.combo_baseline.setCurrentText(r.get("baseline_mode", "none"))
            deriv = r.get("derivative_order", 0)
            self.combo_derivative.setCurrentIndex(min(max(0, int(deriv)), 2))
            self.chk_enabled.setChecked(r.get("enabled", True))
            self.chk_popup.setChecked(r.get("notify_popup", True))
            self.chk_sound.setChecked(r.get("notify_sound", True))
            self.lbl_test_result.setStyleSheet("padding: 8px; border-radius: 4px; background-color: #2e2e2e; color: #dcdcdc; font-weight: bold;")
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
            "density_mode": self.combo_density.currentText(),
            "baseline_mode": self.combo_baseline.currentText(),
            "derivative_order": self.combo_derivative.currentIndex(),
            "enabled": self.chk_enabled.isChecked(),
            "notify_popup": self.chk_popup.isChecked(),
            "notify_sound": self.chk_sound.isChecked(),
        }

    def _on_new_rule(self):
        new_rule = {
            "id": str(uuid.uuid4()),
            "name": "New Alert",
            "dataset_type": "country",
            "entity_filter": "All",
            "condition": "[Total Population] < 1000000",
            "density_mode": "none",
            "baseline_mode": "none",
            "derivative_order": 0,
            "enabled": True,
            "notify_popup": True,
            "notify_sound": True
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
            # Highlight GREEN
            self.lbl_test_result.setStyleSheet("padding: 8px; border-radius: 4px; background-color: #1e4620; color: #7cfc00; font-weight: bold; border: 1px solid #4caf50;")
            most_recent = matches[0]
            self.lbl_test_result.setText(
                f"✓ CONDITION FIRED! Triggered {len(matches)} times. Most recent match: {most_recent['entity']} at Year {most_recent['moment']}."
            )
            for row, m in enumerate(matches[:15]):
                self.table_matches.insertRow(row)
                self.table_matches.setItem(row, 0, QTableWidgetItem(str(m["moment"])))
                self.table_matches.setItem(row, 1, QTableWidgetItem(m["entity"]))
                self.table_matches.setItem(row, 2, QTableWidgetItem(m["condition"]))

        elif status == "NOT_FIRED":
            # Highlight RED
            self.lbl_test_result.setStyleSheet("padding: 8px; border-radius: 4px; background-color: #4a1c1a; color: #ff6b6b; font-weight: bold; border: 1px solid #f44336;")
            self.lbl_test_result.setText("✗ CONDITION NOT FIRED. Criteria not satisfied in any loaded record.")

        else:
            # Highlight DARK RED for error
            self.lbl_test_result.setStyleSheet("padding: 8px; border-radius: 4px; background-color: #3b0000; color: #ff9999; font-weight: bold; border: 1px solid #d32f2f;")
            self.lbl_test_result.setText(f"⚠ ERROR EVALUATING CONDITION: {err_msg}")

    def _on_apply_and_close(self):
        if 0 <= self.current_rule_idx < len(self.rules):
            self.rules[self.current_rule_idx] = self._collect_current_rule()
        save_alerts(self.rules)
        self.accept()