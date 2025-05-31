#!/usr/bin/env python3
from PyQt6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
import sys
from filesutils import FilesUtils

class AutoCloseDialog(QDialog):
    def __init__(self, title, message, timeout_secs=10, icon=None):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(300, 100)

        self.timeout_secs = timeout_secs
        self.remaining = timeout_secs

        layout = QVBoxLayout()

        message_layout = QHBoxLayout()

        if(icon):
            icon_label = QLabel()
            icon_label.setPixmap(QPixmap(FilesUtils.get_asset_path(icon)).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            message_layout.addWidget(icon_label)

        self.message = QLabel(message)
        message_layout.addWidget(self.message)

        layout.addLayout(message_layout)

        self.label = QLabel(f"Closing in {self.remaining} seconds...")
        layout.addWidget(self.label)

        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.manual_accept)
        layout.addWidget(self.ok_button)

        self.setLayout(layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)

    def manual_accept(self):
        self.timer.stop()
        self.accept()

    def update_countdown(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self.accept()
        else:
            self.label.setText(f"Closing in {self.remaining} seconds...")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dlg = AutoCloseDialog(timeout_secs=5)
    if dlg.exec():
        print("OK pressed or dialog closed.")
    else:
        print("Dialog auto-closed.")
