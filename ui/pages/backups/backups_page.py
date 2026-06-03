from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton

from ui.pages.backups.snapshots_page import SnapshotsPage


class BackupsPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet(
            """
            QWidget {
                background: transparent;
            }

            QPushButton {
                padding: 8px 14px;
                border-radius: 10px;
                border: 1px solid rgba(31, 92, 255, 120);
                background: rgba(10, 15, 25, 230);
                color: #ecf4ff;
            }

            QPushButton:hover {
                background: rgba(23, 147, 209, 70);
                border: 1px solid rgba(35, 166, 255, 180);
            }

            QLabel#HintLabel {
                color: #9aa6b2;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)

        self.btn_back = QPushButton("← Back to menu")
        self.btn_back.clicked.connect(self.back_requested.emit)

        self.lbl_hotkey = QLabel("Esc returns to the menu too")
        self.lbl_hotkey.setObjectName("HintLabel")
        self.lbl_hotkey.setFont(QFont("DejaVu Sans Mono", 9))
        self.lbl_hotkey.setAlignment(Qt.AlignVCenter | Qt.AlignRight)

        top_row.addWidget(self.btn_back)
        top_row.addStretch(1)
        top_row.addWidget(self.lbl_hotkey)

        header = QFrame()
        header.setStyleSheet("background: transparent; border: none;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)

        title = QLabel("Backups")
        title.setFont(QFont("DejaVu Sans Mono", 22, QFont.Bold))
        title.setStyleSheet("color: #23a6ff;")

        subtitle = QLabel("Create, restore and verify Carbonara snapshots")
        subtitle.setFont(QFont("DejaVu Sans Mono", 10))
        subtitle.setStyleSheet("color: #9aa6b2;")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        self.snapshots_page = SnapshotsPage(self)

        footer = QFrame()
        footer.setStyleSheet("background: transparent; border: none;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(0)

        footer_hint = QLabel("Back to menu: button or Esc")
        footer_hint.setObjectName("HintLabel")
        footer_hint.setFont(QFont("DejaVu Sans Mono", 9))
        footer_hint.setAlignment(Qt.AlignCenter)

        footer_layout.addWidget(footer_hint)

        root.addLayout(top_row)
        root.addWidget(header)
        root.addWidget(self.snapshots_page, 1)
        root.addWidget(footer)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.back_requested.emit()
            return
        super().keyPressEvent(event)
