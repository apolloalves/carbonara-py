from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
)

from ui.pages.backups.snapshots_page import SnapshotsPage


class BackupsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet(
            """
            QWidget {
                background: transparent;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QFrame()
        header.setStyleSheet(
            """
            QFrame {
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 12px;
                background: rgba(8, 12, 20, 220);
            }
            """
        )

        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(4)

        title = QLabel("Backups")
        title.setFont(QFont("DejaVu Sans Mono", 18, QFont.Bold))
        title.setStyleSheet("color: #23a6ff;")

        subtitle = QLabel("Create, restore and verify Carbonara snapshots")
        subtitle.setFont(QFont("DejaVu Sans Mono", 10))
        subtitle.setStyleSheet("color: #9aa6b2;")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        self.snapshots_page = SnapshotsPage(self)

        root.addWidget(header)
        root.addWidget(self.snapshots_page, 1)
