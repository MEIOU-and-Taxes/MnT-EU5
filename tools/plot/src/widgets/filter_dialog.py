from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTableWidget, QHeaderView, \
	QPushButton, QComboBox, QTableWidgetItem


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
