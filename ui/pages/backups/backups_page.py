from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame

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
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(12)

        title = QLabel("Backups")
        title.setFont(QFont("DejaVu Sans Mono", 22, QFont.Bold))
        title.setStyleSheet("color: #23a6ff;")

        subtitle = QLabel("Create, restore and verify Carbonara snapshots")
        subtitle.setFont(QFont("DejaVu Sans Mono", 10))
        subtitle.setStyleSheet("color: #9aa6b2;")

        top = QFrame()
        top.setStyleSheet("background: transparent; border: none;")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(2)
        top_layout.addWidget(title)
        top_layout.addWidget(subtitle)

        self.snapshots_page = SnapshotsPage(self)

        root.addWidget(top)
        root.addWidget(self.snapshots_page, 1)
