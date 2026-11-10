from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QHeaderView,
    QPushButton, QComboBox, QTableWidgetItem, QMessageBox, QTextEdit
)
from src.parsing.computed_series import (
    load_raw_computed_series_rows, save_computed_series_rows, validate_expression, check_missing_variables
)
from src.widgets.formula_completer import FormulaItemDelegate

DATASET_OPTIONS = ["country", "market", "region"]

REFERENCE_TEXT = """<b>Supported Operators:</b> +, -, *, /, //, %, ^ (power), parentheses ( ), and [Variable With Spaces].
<br><b>Country Variables:</b> income, total_debt, army_size, navy_size, Supply, Demand, Population, locations, num_locations, control_avg, prestige, stability, etc.
<br><b>Market Variables:</b> Food, Food Stockpile, Max Food Stockpile, Monthly Food, Food Price, Total Value Traded, Merchant Capacity, Burgher Trade Capacity, Locations, Population, etc.
<br><b>Region Variables:</b> Total population, Average literacy, Average prosperity, locations, road types (Gravel Road, Paved Road), goods (Food price, Silk price), buildings (Castle, University), etc.
"""


class ComputedSeriesDialog(QDialog):
    """Dialog for editing computed_series.csv with validation before saving."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Computed Series Formulas")
        self.resize(1020, 620)

        main_layout = QVBoxLayout(self)

        header = QLabel("<h3>Computed Series Formulas</h3>Configure derived mathematical metrics calculated across datasets.")
        main_layout.addWidget(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Dataset Type", "New Metric Name", "Expression (Formula)", "Description"])
        self.table.verticalHeader().setVisible(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        main_layout.addWidget(self.table)

        # Row actions
        row_btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Formula")
        self.btn_add.clicked.connect(self._on_add_row)
        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.clicked.connect(self._on_delete_row)
        self.btn_up = QPushButton("Move Up")
        self.btn_up.clicked.connect(self._on_move_up)
        self.btn_down = QPushButton("Move Down")
        self.btn_down.clicked.connect(self._on_move_down)
        self.btn_validate = QPushButton("Validate Formulas")
        self.btn_validate.clicked.connect(lambda: self.validate_all(show_success_popup=True))

        row_btn_layout.addWidget(self.btn_add)
        row_btn_layout.addWidget(self.btn_delete)
        row_btn_layout.addWidget(self.btn_up)
        row_btn_layout.addWidget(self.btn_down)
        row_btn_layout.addStretch()
        row_btn_layout.addWidget(self.btn_validate)
        main_layout.addLayout(row_btn_layout)

        # Reference helper
        self.ref_box = QTextEdit()
        self.ref_box.setReadOnly(True)
        self.ref_box.setFixedHeight(85)
        self.ref_box.setHtml(REFERENCE_TEXT)
        self.ref_box.setStyleSheet("background-color: #242424; color: #cfcfcf; border-radius: 4px; padding: 4px;")
        main_layout.addWidget(self.ref_box)

        # Status and bottom buttons
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #888888; font-style: italic;")
        main_layout.addWidget(self.lbl_status)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.btn_save = QPushButton("Save and Apply")
        self.btn_save.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.btn_save.clicked.connect(self._on_save_and_apply)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_save)
        bottom_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(bottom_layout)

        self._populate_rows(load_raw_computed_series_rows())

        self.table.setItemDelegateForColumn(
            2,
            FormulaItemDelegate(
                get_dataset_type_fn=lambda row: self._get_row_data(row)["dataset_type"],
                parent=self.table
            )
        )

    def _populate_rows(self, rows):
        self.table.setRowCount(0)
        for r in rows:
            self._insert_row_item(r.get("dataset_type", "country"),
                                  r.get("new_metric_name", ""),
                                  r.get("expression", ""),
                                  r.get("description", ""))

    def _insert_row_item(self, dataset_type, name, expr, desc):
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)

        combo = QComboBox()
        combo.addItems(DATASET_OPTIONS)
        clean_type = dataset_type.lower().strip()
        idx = combo.findText(clean_type)
        combo.setCurrentIndex(idx if idx != -1 else 0)
        self.table.setCellWidget(row_idx, 0, combo)

        self.table.setItem(row_idx, 1, QTableWidgetItem(name))
        self.table.setItem(row_idx, 2, QTableWidgetItem(expr))
        self.table.setItem(row_idx, 3, QTableWidgetItem(desc))

    def _on_add_row(self):
        self._insert_row_item("country", "New Metric", "var1 / var2", "Description")
        self.table.selectRow(self.table.rowCount() - 1)

    def _on_delete_row(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        for r in sorted([s.row() for s in sel], reverse=True):
            self.table.removeRow(r)

    def _on_move_up(self):
        r = self.table.currentRow()
        if r > 0:
            self._swap_rows(r, r - 1)
            self.table.selectRow(r - 1)

    def _on_move_down(self):
        r = self.table.currentRow()
        if 0 <= r < self.table.rowCount() - 1:
            self._swap_rows(r, r + 1)
            self.table.selectRow(r + 1)

    def _swap_rows(self, r1, r2):
        row1_data = self._get_row_data(r1)
        row2_data = self._get_row_data(r2)
        self._set_row_data(r1, row2_data)
        self._set_row_data(r2, row1_data)

    def _get_row_data(self, row):
        combo = self.table.cellWidget(row, 0)
        d_type = combo.currentText() if combo else "country"
        name = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
        expr = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
        desc = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
        return {"dataset_type": d_type, "new_metric_name": name, "expression": expr, "description": desc}

    def _set_row_data(self, row, data):
        combo = self.table.cellWidget(row, 0)
        if combo:
            idx = combo.findText(data["dataset_type"])
            if idx != -1:
                combo.setCurrentIndex(idx)
        self.table.setItem(row, 1, QTableWidgetItem(data["new_metric_name"]))
        self.table.setItem(row, 2, QTableWidgetItem(data["expression"]))
        self.table.setItem(row, 3, QTableWidgetItem(data["description"]))

    def get_table_rows(self):
        rows = []
        for r in range(self.table.rowCount()):
            rows.append(self._get_row_data(r))
        return rows

    def validate_all(self, show_success_popup=False):
        errors = []
        rows = self.get_table_rows()
        prior_names_by_type = {}

        err_bg = QColor("#7a1f1d")
        err_fg = QColor("#ffffff")

        # Reset all highlighting first
        for r in range(self.table.rowCount()):
            for c in range(1, 4):
                item = self.table.item(r, c)
                if item:
                    item.setData(Qt.ItemDataRole.BackgroundRole, None)
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)
                    item.setToolTip("")

        for idx, row in enumerate(rows, start=1):
            r_idx = idx - 1
            d_type = row["dataset_type"].strip().lower()
            name = row["new_metric_name"].strip()
            expr = row["expression"].strip()

            item_name = self.table.item(r_idx, 1)
            item_expr = self.table.item(r_idx, 2)
            row_has_error = False

            if not d_type:
                errors.append(f"Row {idx}: Dataset Type cannot be empty.")
                row_has_error = True
            elif d_type not in DATASET_OPTIONS:
                errors.append(f"Row {idx}: Invalid dataset type '{d_type}'. Must be one of {DATASET_OPTIONS}.")
                row_has_error = True

            if not name:
                errors.append(f"Row {idx}: Metric Name cannot be empty.")
                if item_name:
                    item_name.setBackground(err_bg)
                    item_name.setForeground(err_fg)
                    item_name.setToolTip("Metric Name cannot be empty.")
                row_has_error = True

            if not expr:
                errors.append(f"Row {idx}: Expression cannot be empty.")
                if item_expr:
                    item_expr.setBackground(err_bg)
                    item_expr.setForeground(err_fg)
                    item_expr.setToolTip("Expression cannot be empty.")
                row_has_error = True
            else:
                try:
                    clean_expr, var_map = validate_expression(expr)
                    priors = prior_names_by_type.get(d_type, [])
                    missing_vars = check_missing_variables(clean_expr, var_map, d_type, priors)
                    if missing_vars:
                        err_text = f"Unknown variable(s) in {d_type} dataset: {', '.join(missing_vars)}. If there is no dataset, the software might not be aware of it."
                        errors.append(f"Row {idx} ('{name or 'Unnamed'}'): {err_text}")
                        if item_expr:
                            item_expr.setBackground(err_bg)
                            item_expr.setForeground(err_fg)
                            item_expr.setToolTip(err_text)
                        row_has_error = True
                except Exception as e:
                    errors.append(f"Row {idx} ('{name or 'Unnamed'}'): {e}")
                    if item_expr:
                        item_expr.setBackground(err_bg)
                        item_expr.setForeground(err_fg)
                        item_expr.setToolTip(str(e))
                    row_has_error = True

            if not row_has_error and name:
                prior_names_by_type.setdefault(d_type, []).append(name)

        if errors:
            self.lbl_status.setStyleSheet("color: #ff6b6b; font-weight: bold;")
            self.lbl_status.setText(f"Validation failed with {len(errors)} error(s). Hover highlighted cells for details.")
            return False, errors
        else:
            self.lbl_status.setStyleSheet("color: #51cf66; font-weight: bold;")
            self.lbl_status.setText(f"✓ All {len(rows)} formula(s) are valid!")
            return True, []

    def _on_save_and_apply(self):
        valid, errors = self.validate_all(show_success_popup=False)
        if not valid:
            err_preview = "\n".join(errors[:10])
            if len(errors) > 10:
                err_preview += f"\n... and {len(errors) - 10} more error(s)."
            QMessageBox.critical(self, "Validation Error", f"Cannot apply invalid formulas:\n\n{err_preview}")
            return

        save_computed_series_rows(self.get_table_rows())
        self.accept()