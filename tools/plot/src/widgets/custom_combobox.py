from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox

class RightClickableComboBox(QComboBox):
    """QComboBox that resets selection to index 0 on right click and displays a 5x taller dropdown."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Default Qt maxVisibleItems is 10; 50 is 5x taller
        self.setMaxVisibleItems(50)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.RightButton:
            self.setCurrentIndex(0)