from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar


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
