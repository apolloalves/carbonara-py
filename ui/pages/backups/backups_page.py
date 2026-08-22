from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QDialog

from ui.pages.backups.snapshots_page import SnapshotsPage, icon_badge, _SyncStatusBadge, _ScheduledSyncDialog


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
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)

        from ui.main_window import AppHeaderBlock  # import adiado — evita import circular

        self.app_header = AppHeaderBlock(back_button=True)
        self.app_header.back_clicked.connect(self.back_requested.emit)
        root.addWidget(self.app_header)

        header = QFrame()
        header.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 14, 0, 0)
        header_layout.setSpacing(14)

        self.header_icon = icon_badge("mdi6.history", 48, color="#23a6ff", bg_rgba="35, 166, 255, 34")

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

        # ── Badge de sincronização automática — clique abre o diálogo
        # de configuração. Ainda SOMENTE UI (sem systemd/backend real).
        self._sync_config: dict = {
            "enabled": False,
            "frequency": "daily",
            "time": "03:00",
            "scope": "both",
        }
        self.sync_badge = _SyncStatusBadge(self)
        self.sync_badge.clicked.connect(self._open_sync_dialog)
        header_layout.addWidget(self.sync_badge)

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

    def _open_sync_dialog(self) -> None:
        dialog = _ScheduledSyncDialog(self._sync_config, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._sync_config = dialog.result_config
            next_run = self._sync_config.get("time") if self._sync_config.get("enabled") else None
            self.sync_badge.set_state(enabled=self._sync_config.get("enabled", False), next_run=next_run)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.back_requested.emit()
            return
        super().keyPressEvent(event)

