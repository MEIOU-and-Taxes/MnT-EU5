from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox

class RightClickableComboBox(QComboBox):
    """QComboBox that resets selection to index 0 on right click."""
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.RightButton:
            self.setCurrentIndex(0)