from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QHeaderView, QTableWidgetItem


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
