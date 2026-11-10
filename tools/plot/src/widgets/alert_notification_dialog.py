from datetime import datetime
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QHeaderView,
    QPushButton, QTableWidgetItem
)


class AlertWindow(QWidget):
    """Separate on-top window with a clearable notification table."""

    def __init__(self, parent=None):
        super().__init__(None)  # Top-level window
        self.setWindowTitle("Triggered Alerts History")
        self.resize(800, 420)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        header = QLabel("<h3>Triggered Alerts Log</h3>")
        header_layout.addWidget(header)
        header_layout.addStretch()

        self.btn_clear = QPushButton("Clear History")
        self.btn_clear.clicked.connect(self.clear_alerts)
        header_layout.addWidget(self.btn_clear)
        layout.addLayout(header_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Trigger Time", "Alert Name", "Year", "Entity", "Condition"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table)

    def add_alerts(self, fired_alerts: list):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.table.setSortingEnabled(False)
        for a in fired_alerts:
            row = 0
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(current_time))
            self.table.setItem(row, 1, QTableWidgetItem(a.get("rule_name", "Alert")))
            self.table.setItem(row, 2, QTableWidgetItem(str(a.get("moment", ""))))
            self.table.setItem(row, 3, QTableWidgetItem(str(a.get("entity", ""))))
            self.table.setItem(row, 4, QTableWidgetItem(str(a.get("condition", ""))))

        self.show()
        self.raise_()
        self.activateWindow()

    def clear_alerts(self):
        self.table.setRowCount(0)