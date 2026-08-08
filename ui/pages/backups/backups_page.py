from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton

from ui.pages.backups.snapshots_page import SnapshotsPage, icon_badge


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

        from ui.main_window import TopHeader  # import adiado — evita import circular

        self.top_header = TopHeader(back_button=True)
        self.top_header.back_clicked.connect(self.back_requested.emit)
        root.addWidget(self.top_header)

        header = QFrame()
        header.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)

        self.header_icon = icon_badge("mdi6.harddisk", 48, color="#23a6ff", bg_rgba="35, 166, 255, 34")

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(2)

        title = QLabel("Timeshift")
        title.setFont(QFont("DejaVu Sans Mono", 22, QFont.Bold))
        title.setStyleSheet("color: #23a6ff;")

        subtitle = QLabel("Create, restore and verify Carbonara snapshots")
        subtitle.setFont(QFont("DejaVu Sans Mono", 10))
        subtitle.setStyleSheet("color: #9aa6b2;")

        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        header_layout.addWidget(self.header_icon)
        header_layout.addLayout(title_block)
        header_layout.addStretch(1)

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

        root.addWidget(header)
        root.addWidget(self.snapshots_page, 1)
        root.addWidget(footer)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.back_requested.emit()
            return
        super().keyPressEvent(event)

