import os
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QHBoxLayout, QSlider, QLabel,
    QCheckBox, QPushButton, QLineEdit, QFileDialog
)

from src.constants import APPDATA_DIR


class SettingsDialog(QDialog):
    """Settings modal dialog for configuring intervals, smoothing, sounds, and opening %appdata%."""
    def __init__(self, current_refresh_idx, current_autosave_idx, current_period, stats_shading_all=True, alarm_sound_path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.combo_refresh = QComboBox()
        self.combo_refresh.addItems(["Refresh: 10s", "Refresh: 30s", "Refresh: 60s", "Refresh: 300s", "Refresh: 600s", "Refresh: Off"])
        self.combo_refresh.setCurrentIndex(current_refresh_idx)
        form_layout.addRow("Graph Refresh Interval:", self.combo_refresh)

        self.combo_autosave = QComboBox()
        self.combo_autosave.addItems(["Auto-save: 1m", "Auto-save: 5m", "Auto-save: 10m", "No auto-save"])
        self.combo_autosave.setCurrentIndex(current_autosave_idx)
        form_layout.addRow("Session Auto-Save Interval:", self.combo_autosave)

        slider_layout = QHBoxLayout()
        self.slider_period = QSlider(Qt.Orientation.Horizontal)
        self.slider_period.setRange(2, 50)
        self.slider_period.setValue(current_period)
        self.lbl_period = QLabel(str(current_period))
        self.slider_period.valueChanged.connect(lambda v: self.lbl_period.setText(str(v)))
        slider_layout.addWidget(self.slider_period)
        slider_layout.addWidget(self.lbl_period)
        form_layout.addRow("Moving Average Period:", slider_layout)

        # Alarm Sound File Picker
        sound_layout = QHBoxLayout()
        self.edit_sound_path = QLineEdit(alarm_sound_path)
        self.edit_sound_path.setPlaceholderText("Default system beep (or pick .wav file)")
        btn_browse_sound = QPushButton("Browse...")
        btn_browse_sound.clicked.connect(self._browse_sound)
        sound_layout.addWidget(self.edit_sound_path)
        sound_layout.addWidget(btn_browse_sound)
        form_layout.addRow("Alarm Sound File (.wav):", sound_layout)

        # Percentile Shading Mode toggle
        self.chk_stats_shading_all = QCheckBox("Shade all percentile bands (Yellow IQR, redder high, greener low)")
        self.chk_stats_shading_all.setChecked(stats_shading_all)
        form_layout.addRow("Percentile Shading:", self.chk_stats_shading_all)

        layout.addLayout(form_layout)

        btn_appdata = QPushButton("Open AppData Folder")
        btn_appdata.clicked.connect(self._open_appdata)
        layout.addWidget(btn_appdata)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _browse_sound(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Alarm Sound", "", "Audio Files (*.wav);;All Files (*.*)")
        if f:
            self.edit_sound_path.setText(f)

    def _open_appdata(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(APPDATA_DIR))

    def get_settings(self):
        return {
            "refresh_idx": self.combo_refresh.currentIndex(),
            "autosave_idx": self.combo_autosave.currentIndex(),
            "period": self.slider_period.value(),
            "stats_shading_all": self.chk_stats_shading_all.isChecked(),
            "alarm_sound_path": self.edit_sound_path.text().strip()
        }
