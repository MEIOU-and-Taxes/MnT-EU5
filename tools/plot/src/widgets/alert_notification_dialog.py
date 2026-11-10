from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QHeaderView,
    QPushButton, QTableWidgetItem
)


class AlertNotificationDialog(QDialog):
    """Notification modal dialog displaying fired alert events."""

    def __init__(self, fired_alerts: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ Alert Triggered!")
        self.resize(720, 380)

        layout = QVBoxLayout(self)

        hdr = QLabel(f"<h3>⚠️ {len(fired_alerts)} Alert Condition(s) Met!</h3>The following conditions were satisfied:")
        layout.addWidget(hdr)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Alert Name", "Moment / Year", "Entity", "Condition"])
        table.setRowCount(len(fired_alerts))
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        for row, a in enumerate(fired_alerts):
            table.setItem(row, 0, QTableWidgetItem(a.get("rule_name", "Alert")))
            table.setItem(row, 1, QTableWidgetItem(str(a.get("moment", ""))))
            table.setItem(row, 2, QTableWidgetItem(str(a.get("entity", ""))))
            table.setItem(row, 3, QTableWidgetItem(str(a.get("condition", ""))))

        layout.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("Acknowledge")
        btn_ok.setStyleSheet("font-weight: bold; padding: 6px 20px;")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)