from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox

# --- Custom Widgets ---
class RightClickableComboBox(QComboBox):
	"""
	A custom QComboBox that resets its selection to the first item when right-clicked
	"""
	def mousePressEvent(self, event):
		# Call the parent's event handler to ensure that normal left-clicks and other events are not broken
		super().mousePressEvent(event)

		# Check if the button that was pressed is the right mouse button
		if event.button() == Qt.MouseButton.RightButton:
			# Set the current index to 0 (the "All" option)
			self.setCurrentIndex(0)
