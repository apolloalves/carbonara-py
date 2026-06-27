from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List
import json
import os
import shutil
import subprocess
import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QThread
from PySide6.QtGui import QFont

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QFrame,
    QComboBox,
    QListView,
    QScrollArea,
    QSizePolicy,
    QDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QAbstractItemView,
    QSplitter,
    QProgressBar,
    QPlainTextEdit,
)

from core.operation_manager import OperationManager
from core.system.storage import (
    StorageDestination,
    format_gb,
    list_backup_destinations,
)

#Material Icons
DEST_GLYPH      = "mdi6.harddisk"
ROOT_GLYPH      = ""
HOME_GLYPH      = ""
BOTH_GLYPH      = ""

RESTORE_GLYPH   = "mdi6.file-restore-outline"
SYNC_GLYPH      = "mdi6.sync"
DELETE_GLYPH    = "mdi6.delete"

REFRESH_GLYPH   = "mdi6.refresh"
CREATE_GLYPH    = "mdi6.folder-multiple"

SNAPSHOT_GLYPH  = "mdi6.archive"



@dataclass(frozen=True)
class SnapshotEntry:
    kind: str
    path: Path
    meta_text: str
    modified_text: str
    size_str: str = ""
    synced_at: str = ""


def read_snapshot_metadata(path: Path) -> dict:
    meta_file = path / "snapshot.json"
    if not meta_file.exists():
        return {}

    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def collect_snapshots(backup_root: Path) -> List[SnapshotEntry]:
    entries: List[SnapshotEntry] = []

    if not backup_root.exists():
        return entries

    for kind_dir in backup_root.iterdir():
        if not kind_dir.is_dir():
            continue

        for snap in sorted(
            [p for p in kind_dir.iterdir() if p.is_dir() and p.name != "latest"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                stat = snap.stat()
                meta = read_snapshot_metadata(snap)

                created_at = meta.get("created_at") or datetime.fromtimestamp(
                    stat.st_mtime
                ).strftime("%Y-%m-%d %H:%M:%S")

                status = meta.get("status", "unknown")

                # Ignora snapshots incompletos (processo cancelado ou travado)
                if status in ("running", "failed"):
                    continue

                source = meta.get("source", "")
                size_bytes = meta.get("size_bytes", 0)
                size_str = ""
                if size_bytes and size_bytes > 0:
                    gb = size_bytes / (1024 ** 3)
                    if gb >= 1:
                        size_str = f"{gb:.1f} GB"
                    else:
                        size_str = f"{size_bytes / (1024 ** 2):.0f} MB"

                meta_text = f"{created_at} • {status}"
                if source:
                    meta_text = f"{meta_text} • {source}"

                synced_at = meta.get("synced_at", "")

                entries.append(
                    SnapshotEntry(
                        kind=kind_dir.name,
                        path=snap,
                        meta_text=meta_text,
                        modified_text=datetime.fromtimestamp(
                            stat.st_mtime
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                        size_str=size_str,
                        synced_at=synced_at,
                    )
                )
            except OSError:
                continue

    return entries


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()

        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)
            child_layout.deleteLater()

def icon_badge(icon_name: str, size: int = 34) -> QLabel:
    label = QLabel()
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(size, size)

    pixmap = qta.icon(
        icon_name,
        color="#FFFFFF"
    ).pixmap(size - 2, size - 2)

    label.setPixmap(pixmap)

    label.setStyleSheet(
        """
        QLabel {
            background: rgba(35, 166, 255, 34);
            border-radius: 10px;
        }
        """
    )

    return label

def style_combo_popup(combo: QComboBox) -> None:
    view = combo.view()
    view.setMouseTracking(True)
    view.viewport().setMouseTracking(True)
    view.setAttribute(Qt.WA_Hover, True)
    view.viewport().setAttribute(Qt.WA_Hover, True)
    view.setUniformItemSizes(True)
    view.setStyleSheet(
        """
        QListView {
            background: #0a0f19;
            color: #ecf4ff;
            border: 1px solid rgba(31, 92, 255, 140);
            outline: 0;
            padding: 4px;
        }

        QListView::item {
            min-height: 32px;
            padding: 8px 10px;
            border-radius: 6px;
        }

        QListView::item:hover {
            background: rgba(35, 166, 255, 70);
            color: #ecf4ff;
        }

        QListView::item:selected {
            background: rgba(35, 166, 255, 180);
            color: #08111d;
        }

        QListView::item:selected:hover {
            background: rgba(70, 188, 255, 220);
            color: #08111d;
        }
        """
    )


class ScopeCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, title: str, subtitle: str, glyph: str, parent=None):
        super().__init__(parent)
        self.key = key

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(96)
        self.setProperty("active", False)

        self.setStyleSheet(
            """
            QFrame {
                background: transparent;
                border: none;
            }

            QPushButton {
                background: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 12px;
                color: #8b92a3;
                font: 700 10pt "DejaVu Sans Mono";
                padding: 0px 12px;
                min-height: 34px;
            }

            QPushButton:hover {
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 22);
                color: #c8d4e0;
            }

            QPushButton:checked {
                background: rgba(59, 130, 246, 0.22);
                border: 1px solid rgba(99, 140, 255, 130);
                color: #ffffff;
            }

            QLabel#ScopeSubtitle {
                color: #5a6a7a;
                background: transparent;
                border: none;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)

        self.btn = QPushButton(f"{glyph}  {title}")
        self.btn.setMinimumHeight(44)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setFocusPolicy(Qt.StrongFocus)
        self.btn.setCheckable(True)
        self.btn.clicked.connect(self._emit_clicked)

        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("ScopeSubtitle")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setFont(QFont("DejaVu Sans Mono", 9))
        self.subtitle.setWordWrap(False)
        self.subtitle.setToolTip(subtitle)
        self.subtitle.setTextInteractionFlags(Qt.NoTextInteraction)

        root.addWidget(self.btn)
        root.addWidget(self.subtitle)

    def _emit_clicked(self):
        self.clicked.emit(self.key)

    def set_active(self, active: bool):
        self.btn.setChecked(active)
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.btn.click()
            self.clicked.emit(self.key)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.btn.click()
            self.clicked.emit(self.key)
            event.accept()
            return
        super().keyPressEvent(event)


class SnapshotCard(QFrame):
    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.entry = entry

        self.setObjectName("SnapshotCard")
        self.setStyleSheet(
            """
            QFrame#SnapshotCard {
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 14px;
                background: rgba(255, 255, 255, 6);
            }
            QFrame#SnapshotCard:hover {
                border: 1px solid rgba(255, 255, 255, 22);
                background: rgba(255, 255, 255, 9);
            }

            QPushButton {
                padding: 0px 22px;
                border-radius: 9px;
                border: 1px solid rgba(255, 255, 255, 14);
                background: rgba(255, 255, 255, 6);
                color: #c8d4e0;
                font: 700 9pt "DejaVu Sans Mono";
                min-height: 34px;
            }

            QPushButton:hover {
                background: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 28);
                color: #ecf4ff;
            }

            QPushButton#DangerButton {
                border: 1px solid rgba(200, 60, 60, 100);
                color: #c8d4e0;
            }

            QPushButton#DangerButton:hover {
                background: rgba(200, 60, 60, 40);
                border: 1px solid rgba(255, 100, 100, 180);
                color: #ffaaaa;
            }

            QPushButton#RestoreButton {
                border: 1px solid rgba(35, 166, 255, 110);
                color: #c8d4e0;
            }

            QPushButton#RestoreButton:hover {
                background: rgba(35, 166, 255, 40);
                border: 1px solid rgba(70, 188, 255, 200);
                color: #8fd4ff;
            }

            QPushButton#SyncButton {
                border: 1px solid rgba(74, 222, 128, 100);
                color: #c8d4e0;
            }

            QPushButton#SyncButton:hover {
                background: rgba(74, 222, 128, 35);
                border: 1px solid rgba(94, 234, 149, 200);
                color: #9bf0bd;
            }
            """
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(18)

        left = QHBoxLayout()
        left.setSpacing(16)

        icon_label = icon_badge(SNAPSHOT_GLYPH, 38)

        text_block = QVBoxLayout()
        text_block.setSpacing(4)

        title = QLabel(entry.path.name)
        title_font = QFont("DejaVu Sans Mono")
        title_font.setPointSizeF(10.5)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ecf4ff;")

        # Linha de meta + tamanho em destaque
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        meta_row.setContentsMargins(0, 0, 0, 0)

        meta = QLabel(entry.meta_text)
        meta.setFont(QFont("DejaVu Sans Mono", 10))
        meta.setStyleSheet("color: #6b7a8d;")
        meta_row.addWidget(meta)

        if entry.size_str:
            size_prefix = QLabel("snapshot size")
            size_prefix.setFont(QFont("DejaVu Sans Mono", 9))
            size_prefix.setStyleSheet("color: #6b7a8d;")
            meta_row.addWidget(size_prefix)

            size_val = QLabel(entry.size_str)
            size_val.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
            size_val.setStyleSheet("color: #4ade80;")
            meta_row.addWidget(size_val)

        meta_row.addStretch()

        text_block.addWidget(title)
        text_block.addLayout(meta_row)

        # Linha synced_at — só aparece se já foi sincronizado
        if entry.synced_at:
            sync_row = QHBoxLayout()
            sync_row.setSpacing(6)
            sync_row.setContentsMargins(0, 0, 0, 0)

            sync_icon = QLabel()
            sync_icon.setPixmap(
                qta.icon(SYNC_GLYPH, color="#23a6ff").pixmap(14, 14)
            )
            sync_lbl = QLabel(f"last sync  {entry.synced_at}")
            sync_lbl.setFont(QFont("DejaVu Sans Mono", 9))
            sync_lbl.setStyleSheet("color: #23a6ff;")

            sync_row.addWidget(sync_icon)
            sync_row.addWidget(sync_lbl)
            sync_row.addStretch()
            text_block.addLayout(sync_row)

        left.addWidget(icon_label)
        left.addLayout(text_block)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_restore = QPushButton("RESTORE")
        self.btn_restore.setIcon(qta.icon(RESTORE_GLYPH, color="#8fd4ff"))
        self.btn_restore.setIconSize(QSize(18, 18))
        self.btn_restore.setObjectName("RestoreButton")

        self.btn_sync = QPushButton("SYNC")
        self.btn_sync.setIcon(qta.icon(SYNC_GLYPH, color="#9bf0bd"))
        self.btn_sync.setIconSize(QSize(18, 18))
        self.btn_sync.setObjectName("SyncButton")

        self.btn_delete = QPushButton("DELETE")
        self.btn_delete.setIcon(qta.icon(DELETE_GLYPH, color="#ff8888"))
        self.btn_delete.setIconSize(QSize(18, 18))
        self.btn_delete.setObjectName("DangerButton")

        btn_row.addWidget(self.btn_restore)
        btn_row.addWidget(self.btn_sync)
        btn_row.addWidget(self.btn_delete)

        root.addLayout(left, 1)
        root.addLayout(btn_row)


class SectionCard(QFrame):
    def __init__(self, title_text: str, path_text: str, glyph: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SectionCard")
        self.setStyleSheet(
            """
            QFrame#SectionCard {
                border: none;
                border-radius: 0px;
                background: transparent;
            }
            """
        )

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(8)

        head_frame = QFrame()
        head_frame.setObjectName("SectionHeader")
        head_frame.setStyleSheet(
            """
            QFrame#SectionHeader {
                border: none;
                border-left: 3px solid rgba(31, 141, 218, 200);
                border-radius: 0px;
                background: transparent;
            }
            """
        )
        head_layout = QHBoxLayout(head_frame)
        head_layout.setContentsMargins(12, 4, 0, 4)
        head_layout.setSpacing(10)

        icon_label = icon_badge(glyph if glyph else CREATE_GLYPH, 32)

        labels = QVBoxLayout()
        labels.setSpacing(1)

        title = QLabel(title_text)
        title.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        title.setStyleSheet("color: #ecf4ff;")

        path = QLabel(path_text)
        path.setFont(QFont("DejaVu Sans Mono", 8))
        path.setStyleSheet("color: #6b7a8d;")

        labels.addWidget(title)
        labels.addWidget(path)

        head_layout.addWidget(icon_label)
        head_layout.addLayout(labels)
        head_layout.addStretch(1)

        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        self.body.setContentsMargins(0, 0, 0, 0)

        self.layout_main.addWidget(head_frame)
        self.layout_main.addLayout(self.body)


class SnapshotsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.entries: list[SnapshotEntry] = []
        self.destinations: list[StorageDestination] = []
        self._backup_proc: subprocess.Popen | None = None
        self.scope = "both"
        self.scope_cards: dict[str, ScopeCard] = {}

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_backup_process)

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

            QPushButton#PrimaryButton {
                background: rgba(74, 222, 128, 0.88);
                border: 1px solid rgba(74, 222, 128, 1);
                color: #08111d;
                font-weight: bold;
            }

            QPushButton#PrimaryButton:hover {
                background: rgba(94, 234, 149, 1);
                border: 1px solid rgba(94, 234, 149, 1);
            }

            QComboBox {
                background: rgba(10, 15, 25, 230);
                color: #ecf4ff;
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 10px;
                padding: 8px 12px;
                min-height: 28px;
            }

            QComboBox:hover,
            QComboBox:focus {
                border: 1px solid rgba(35, 166, 255, 200);
            }

            QComboBox::drop-down {
                border: none;
                width: 30px;
            }

            QComboBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
            }

            QLabel#Muted {
                color: #9aa6b2;
            }

            QScrollArea {
                border: none;
                background: transparent;
            }

            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.control_card = QFrame()
        self.control_card.setObjectName("ControlCard")
        self.control_card.setStyleSheet(
            """
            QFrame#ControlCard {
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 18px;
                background: rgba(255, 255, 255, 6);
            }
            """
        )
        control_layout = QHBoxLayout(self.control_card)
        control_layout.setContentsMargins(20, 18, 20, 18)
        control_layout.setSpacing(48)
        control_layout.setAlignment(Qt.AlignTop)

        # ── COLUNA ESQUERDA ──
        left_panel = QVBoxLayout()
        left_panel.setSpacing(14)

        destination_block = QVBoxLayout()
        destination_block.setSpacing(8)

        lbl_destination = QLabel("Destination")
        lbl_destination.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl_destination.setStyleSheet("color: #ecf4ff;")

        self.cmb_destination = QComboBox()
        self.cmb_destination.setEditable(False)
        self.cmb_destination.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_destination.setMaxVisibleItems(8)
        self.cmb_destination.setFocusPolicy(Qt.StrongFocus)
        self.cmb_destination.setView(QListView())
        self.cmb_destination.currentIndexChanged.connect(self._on_destination_changed)
        self.cmb_destination.activated[int].connect(self._on_destination_activated)
        style_combo_popup(self.cmb_destination)

        destination_block.addWidget(lbl_destination)
        destination_block.addWidget(self.cmb_destination)

        scope_block = QVBoxLayout()
        scope_block.setSpacing(10)
        scope_block.setContentsMargins(0, -4, 0, 0)

        lbl_scope = QLabel("Scope")
        lbl_scope.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl_scope.setStyleSheet("color: #ecf4ff;")

        scope_cards_row = QHBoxLayout()
        scope_cards_row.setSpacing(10)

        scope_defs = [
            ("root", "ROOT ONLY", "Snapshot only the system root", ROOT_GLYPH),
            ("home", "HOME ONLY", "Snapshot only /home", HOME_GLYPH),
            ("both", "ROOT+HOME", "Snapshot both root and home", BOTH_GLYPH),
        ]

        for key, title, subtitle, glyph in scope_defs:
            card = ScopeCard(key, title, subtitle, glyph)
            card.clicked.connect(self.set_scope)
            self.scope_cards[key] = card
            scope_cards_row.addWidget(card)

        scope_block.addWidget(lbl_scope)
        scope_block.addLayout(scope_cards_row)

        left_panel.addLayout(destination_block)
        left_panel.addLayout(scope_block)

        # ── COLUNA DIREITA ──
        self.right_frame = QFrame()
        self.right_frame.setObjectName("RightPanel")
        self.right_frame.setStyleSheet(
            """
            QFrame#RightPanel {
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 16px;
                background: rgba(255, 255, 255, 6);
            }
            """
        )

        right_panel = QVBoxLayout(self.right_frame)
        right_panel.setContentsMargins(16, 14, 16, 14)
        right_panel.setSpacing(2)

        top_summary = QHBoxLayout()
        top_summary.setSpacing(8)
        top_summary.setAlignment(Qt.AlignVCenter)

        self.destination_badge = icon_badge(DEST_GLYPH, 52)

        summary_text = QVBoxLayout()
        summary_text.setSpacing(0)

        self.lbl_destination_info = QLabel("Select a backup destination")
        self.lbl_destination_info.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        self.lbl_destination_info.setStyleSheet("color: #ecf4ff;")

        self.lbl_destination_meta = QLabel("—")
        self.lbl_destination_meta.setObjectName("Muted")
        self.lbl_destination_meta.setStyleSheet("color: #9aa6b2; margin-top: -1px;")
        self.lbl_destination_meta.setFont(QFont("DejaVu Sans Mono", 9))

        summary_text.addWidget(self.lbl_destination_info)
        summary_text.addWidget(self.lbl_destination_meta)

        top_summary.addWidget(self.destination_badge, 0, Qt.AlignVCenter)
        top_summary.addLayout(summary_text)
        top_summary.addStretch()

        self.space_bar = QFrame()
        self.space_bar.setFixedHeight(5)
        self.space_bar.setStyleSheet("""
        QFrame {
            border: none;
            border-radius: 3px;
            background: rgba(255,255,255,18);
        }
        """)

        self.space_fill = QFrame(self.space_bar)
        self.space_fill.setGeometry(0, 0, 0, 5)
        self.space_fill.setStyleSheet("""
        QFrame {
            border: none;
            border-radius: 3px;
            background: rgba(35,166,255,210);
        }
        """)

        self.lbl_space_percent = QLabel("—")
        self.lbl_space_percent.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        self.lbl_space_percent.setStyleSheet("color: #4ade80;")

        space_row = QHBoxLayout()
        space_row.setSpacing(10)
        space_row.setContentsMargins(0, 8, 0, 0)
        space_row.addWidget(self.space_bar, 8)
        space_row.addWidget(self.lbl_space_percent, 1)

        right_panel.addLayout(top_summary)
        right_panel.addLayout(space_row)

        # botões FORA do right_frame
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(12)

        self.btn_refresh = QPushButton("REFRESH")
        self.btn_refresh.setIcon(qta.icon(REFRESH_GLYPH, color="#FFFFFF"))
        self.btn_refresh.setIconSize(QSize(16, 16))
        self.btn_refresh.setFixedWidth(140)
        self.btn_refresh.setVisible(False)  # oculto: não faz mais sentido na UI atual

        self.btn_create = QPushButton("CREATE SNAPSHOT")
        self.btn_create.setIcon(qta.icon(CREATE_GLYPH))
        self.btn_create.setIconSize(QSize(16, 16))
        self.btn_create.setFixedWidth(160)
        self.btn_create.setObjectName("PrimaryButton")

        self.btn_refresh.clicked.connect(self.refresh_destinations)
        self.btn_create.clicked.connect(self.create_snapshot)

        buttons_row.addStretch()
        buttons_row.addWidget(self.btn_refresh)
        buttons_row.addWidget(self.btn_create)

        # coluna direita: label + card bordado alinhados com esquerda
        right_column = QVBoxLayout()
        right_column.setSpacing(0)
        right_column.setContentsMargins(0, 0, 0, 0)

        right_column.addWidget(self.right_frame)
        right_column.addSpacing(24)
        right_column.addLayout(buttons_row)

        control_layout.addLayout(left_panel, 5)
        control_layout.addLayout(right_column, 4)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(14)
        self.scroll_layout.addStretch(1)

        self.scroll.setWidget(self.scroll_content)
        sep_line = QFrame()
        sep_line.setFixedHeight(1)
        sep_line.setStyleSheet("background: rgba(255,255,255,6); border: none;")

        root.addWidget(self.control_card)
        root.addWidget(sep_line)
        root.addWidget(self.scroll, 1)

        self.refresh_destinations()
        self.set_scope("both")

    def set_scope(self, scope: str):
        if scope not in {"root", "home", "both"}:
            return
        self.scope = scope
        for key, card in self.scope_cards.items():
            card.set_active(key == scope)

    def current_scope(self) -> str:
        return self.scope if self.scope in {"root", "home", "both"} else "both"

    def current_destination(self) -> StorageDestination | None:
        return self.cmb_destination.currentData()

    def _format_combo_item(self, dest: StorageDestination) -> str:
        return (
            f" {dest.label}  •  {format_gb(dest.free_gb)} livre  •  "
            f"{dest.mountpoint}  •  {dest.fs_type}"
        )

    def refresh_destinations(self):
        current_mount = None
        current = self.current_destination()
        if current is not None:
            current_mount = current.mountpoint

        self.destinations = list_backup_destinations()

        self.cmb_destination.blockSignals(True)
        self.cmb_destination.clear()

        for dest in self.destinations:
            self.cmb_destination.addItem(self._format_combo_item(dest), dest)

        self.cmb_destination.blockSignals(False)

        if not self.destinations:
            self.lbl_destination_info.setText("No backup destinations found")
            self.lbl_destination_meta.setText("Mount a disk under /mnt or /media")
            self.lbl_space_percent.setText("—")
            self.space_fill.setGeometry(0, 0, 0, 5)
            self.btn_create.setEnabled(False)
            self.rebuild_snapshot_view()
            return

        self.btn_create.setEnabled(True)

        if current_mount:
            idx = next(
                (i for i, d in enumerate(self.destinations) if d.mountpoint == current_mount),
                0,
            )
            self.cmb_destination.setCurrentIndex(idx)
        else:
            self.cmb_destination.setCurrentIndex(0)

        self.update_destination_summary()
        self.rebuild_snapshot_view()

    def _on_destination_changed(self, index: int):
        if index < 0:
            self.lbl_space_percent.setText("—")
            return
        self.update_destination_summary()

    def _on_destination_activated(self, index: int):
        if index < 0:
            return
        self.update_destination_summary()
        self.rebuild_snapshot_view()

    def update_destination_summary(self):
        dest = self.current_destination()
        if dest is None:
            self.lbl_destination_info.setText("Select a backup destination")
            self.lbl_destination_meta.setText("—")
            self.lbl_space_percent.setText("—")
            self.space_fill.setGeometry(0, 0, 0, 5)
            return

        used_pct = 0
        if dest.total_bytes > 0:
            used_pct = int(round((dest.used_bytes / dest.total_bytes) * 100))

        free_pct = max(0, 100 - used_pct)
        fill_width = max(0, int(self.space_bar.width() * used_pct / 100))
        self.space_fill.setGeometry(0, 0, fill_width, 5)

        self.lbl_destination_info.setText(dest.label)
        self.lbl_destination_meta.setText(
            f"{format_gb(dest.free_gb)} livre de {format_gb(dest.total_gb)} • "
            f"{dest.mountpoint} • {dest.fs_type}"
        )
        self.lbl_space_percent.setText(f"{free_pct}% livre")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_destination_summary()

    def current_backup_root(self) -> Path | None:
        dest = self.current_destination()
        if dest is None:
            return None
        return Path(dest.backup_root)

    def set_busy(self, busy: bool):
        self.cmb_destination.setEnabled(not busy)
        self.btn_refresh.setEnabled(not busy)
        self.btn_create.setEnabled(not busy)
        self.scroll.setEnabled(not busy)
        for card in self.scope_cards.values():
            card.setEnabled(not busy)

    def rebuild_snapshot_view(self):
        clear_layout(self.scroll_layout)

        backup_root = self.current_backup_root()
        if backup_root is None:
            self.scroll_layout.addStretch(1)
            return

        entries = collect_snapshots(backup_root)

        if not entries:
            empty = QFrame()
            empty.setObjectName("EmptyState")
            empty.setStyleSheet(
                """
                QFrame#EmptyState {
                    border: 1px solid rgba(31, 92, 255, 55);
                    border-radius: 16px;
                    background: rgba(8, 12, 20, 120);
                }
                QFrame#EmptyState QLabel {
                    border: none;
                    background: transparent;
                }
                """
            )
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(32, 36, 32, 36)
            empty_layout.setSpacing(4)
            empty_layout.setAlignment(Qt.AlignCenter)

            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setFixedSize(48, 48)
            icon_label.setPixmap(qta.icon(SNAPSHOT_GLYPH, color="#3a6a9a").pixmap(28, 28))
            icon_label.setStyleSheet(
                "background: rgba(35, 166, 255, 18); border-radius: 14px;"
            )

            icon_row = QHBoxLayout()
            icon_row.addStretch()
            icon_row.addWidget(icon_label)
            icon_row.addStretch()
            empty_layout.addLayout(icon_row)
            empty_layout.addSpacing(14)

            title = QLabel("No snapshots yet")
            title.setAlignment(Qt.AlignCenter)
            title.setStyleSheet("color: #ecf4ff;")
            title.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
            empty_layout.addWidget(title)

            label = QLabel("Use Create Snapshot above to get started.")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #9aa6b2;")
            label.setFont(QFont("DejaVu Sans Mono", 9))
            empty_layout.addWidget(label)

            self.scroll_layout.addWidget(empty)
            self.scroll_layout.addStretch(1)
            return

        grouped = defaultdict(list)
        for entry in entries:
            grouped[entry.kind.upper()].append(entry)

        ordered_kinds = []
        for preferred in ("ROOT", "HOME"):
            if preferred in grouped:
                ordered_kinds.append(preferred)

        for kind in sorted(grouped.keys()):
            if kind not in ordered_kinds:
                ordered_kinds.append(kind)

        for kind in ordered_kinds:
            section_icon = ROOT_GLYPH if kind == "ROOT" else HOME_GLYPH if kind == "HOME" else SNAPSHOT_GLYPH
            section = SectionCard(
                kind,
                str(backup_root / kind),
                section_icon,
            )
            for entry in grouped[kind]:
                card = SnapshotCard(entry)
                card.btn_restore.clicked.connect(
                    lambda _, e=entry: self.restore_snapshot(e)
                )
                card.btn_sync.clicked.connect(
                    lambda _, e=entry: self.sync_snapshot(e)
                )
                card.btn_delete.clicked.connect(
                    lambda _, e=entry: self.delete_snapshot(e)
                )
                section.body.addWidget(card)

            self.scroll_layout.addWidget(section)

        self.scroll_layout.addStretch(1)

    def refresh_list(self):
        # refresh_destinations relê o disco (bytes livres/usados) e chama
        # rebuild_snapshot_view internamente — garante que o espaço livre
        # exibido no RightPanel reflita o estado real após o backup.
        self.refresh_destinations()

    def create_snapshot(self):
        dest = self.current_destination()
        if dest is None:
            QMessageBox.warning(self, "Carbonara", "Select a destination first.")
            return

        if OperationManager.is_running():
            current = OperationManager.current()
            QMessageBox.warning(
                self,
                "Carbonara",
                f"Another operation is already running: {current.name if current else 'busy'}",
            )
            return

        if not OperationManager.start(
            "backup",
            f"Snapshot on {dest.label} ({dest.mountpoint})",
        ):
            QMessageBox.warning(
                self,
                "Carbonara",
                "Another exclusive operation is already running.",
            )
            return

        self.set_busy(True)

        project_root = Path(__file__).resolve().parents[3]
        python_bin = Path.home() / "venvs" / "pyside" / "bin" / "python3"

        script = f"""
import sys
sys.path.insert(0, {str(project_root)!r})

from PySide6.QtWidgets import QApplication
from core.snapshots.backup import create_backup
from ui.widgets.backup_progress import BackupProgressDialog

app = QApplication([])
dialog = BackupProgressDialog()
create_backup(dialog, destination_mountpoint={dest.mountpoint!r}, scope={self.current_scope()!r})
dialog.exec()
"""

        cmd = [
            "pkexec",
            "env",
            f"DISPLAY={os.environ.get('DISPLAY', '')}",
            f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}",
            f"PYTHONPATH={project_root}",
            str(python_bin),
            "-c",
            script,
        ]

        try:
            self._backup_proc = subprocess.Popen(cmd, cwd=str(project_root))
            self._poll_timer.start()
        except Exception as e:
            OperationManager.finish()
            self.set_busy(False)
            _show_error("Carbonara Backup", str(e), parent=self)

    def _poll_backup_process(self):
        if self._backup_proc is None:
            return

        rc = self._backup_proc.poll()
        if rc is None:
            return

        self._poll_timer.stop()
        self._backup_proc = None
        OperationManager.finish()
        self.set_busy(False)

        # ── PATCH 2: sempre atualiza a lista, depois decide se mostra aviso ──
        self.refresh_list()

        # rc=0   → sucesso silencioso
        # rc=2   → cancelamento intencional pelo usuário (BackupProgressDialog.done(2))
        # rc=126 → pkexec cancelado pelo usuário (ESC ou Cancelar na autenticação)
        # rc<0   → processo terminado por sinal (ex: -6/SIGABRT, -9/SIGKILL),
        #          o que ocorre normalmente ao cancelar/matar o subprocesso
        #          durante um backup em andamento — não é um erro real.
        # rc=outro → erro real
        if rc not in (0, 2, 126) and rc >= 0:
            _show_error(
                "Carbonara Backup",
                f"Backup process exited with code {rc}.",
                parent=self,
            )

    def restore_snapshot(self, entry: SnapshotEntry):
        if OperationManager.is_running():
            QMessageBox.warning(
                self, "Carbonara", "Another exclusive operation is already running."
            )
            return

        dialog = _RestoreDialog(entry, parent=self)
        dialog.exec()

    def sync_snapshot(self, entry: SnapshotEntry):
        if OperationManager.is_running():
            QMessageBox.warning(
                self, "Carbonara", "Another exclusive operation is already running."
            )
            return

        dialog = _SyncConfirmDialog(entry, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        if not OperationManager.start("sync", f"Sync snapshot {entry.path.name}"):
            QMessageBox.warning(self, "Carbonara", "Another operation is already running.")
            return

        self.set_busy(True)

        dest = self.current_destination()
        project_root = Path(__file__).resolve().parents[3]
        python_bin = Path.home() / "venvs" / "pyside" / "bin" / "python3"

        script = f"""
import sys
sys.path.insert(0, {str(project_root)!r})

from PySide6.QtWidgets import QApplication
from core.snapshots.backup import sync_snapshot
from ui.widgets.backup_progress import BackupProgressDialog

app = QApplication([])
dialog = BackupProgressDialog()
sync_snapshot(dialog, snapshot_path={str(entry.path)!r})
dialog.exec()
"""
        cmd = [
            "pkexec",
            "env",
            f"DISPLAY={os.environ.get('DISPLAY', '')}",
            f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}",
            f"PYTHONPATH={project_root}",
            str(python_bin),
            "-c",
            script,
        ]

        try:
            self._backup_proc = subprocess.Popen(cmd, cwd=str(project_root))
            self._poll_timer.start()
        except Exception as e:
            OperationManager.finish()
            self.set_busy(False)
            _show_error("Carbonara Sync", str(e), parent=self)

    def delete_snapshot(self, entry: SnapshotEntry):
        if OperationManager.is_running():
            QMessageBox.warning(
                self,
                "Carbonara",
                "Another exclusive operation is already running.",
            )
            return

        dialog = _DeleteConfirmDialog(entry, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        if not OperationManager.start("delete", f"Delete snapshot {entry.path.name}"):
            QMessageBox.warning(self, "Carbonara", "Another operation is already running.")
            return

        self.set_busy(True)

        # Dialog de progresso — aparece enquanto o worker roda
        self._delete_progress = _DeleteProgressDialog(entry.path.name, parent=self)
        self._delete_progress.show()

        worker = _DeleteWorker(entry.path, parent=self)
        worker.finished_ok.connect(lambda msg: self._on_delete_ok(msg))
        worker.failed.connect(lambda msg: self._on_delete_fail(msg))
        worker.start()
        self._delete_worker = worker

    def _on_delete_ok(self, msg: str) -> None:
        self._delete_progress.close()
        OperationManager.finish()
        self.set_busy(False)
        self.refresh_list()

    def _on_delete_fail(self, msg: str) -> None:
        self._delete_progress.close()
        OperationManager.finish()
        self.set_busy(False)
        _show_error("Delete Snapshot", f"Falha ao remover snapshot:\n\n{msg}", parent=self)
        self.refresh_list()


# ── Shared styled dialogs ─────────────────────────────────────────────────────

class _ErrorDialog(QDialog):
    """Substitui QMessageBox.critical com identidade visual Carbonara."""

    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(640)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(title, message)
        self._apply_styles()
        self.adjustSize()

    def _build_ui(self, title: str, message: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("ErrHeader")
        header.setFixedHeight(46)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 14, 0)

        icon = QLabel()
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.alert-circle", color="#ff6666").pixmap(16, 16))
        icon.setStyleSheet("QLabel { background: rgba(200,60,60,40); border-radius: 7px; }")

        lbl = QLabel(title)
        lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.setFixedSize(24, 24)
        btn_x.mousePressEvent = lambda e: self.accept()


        h_layout.addWidget(icon)
        h_layout.addSpacing(8)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        body = QFrame()
        body.setObjectName("ErrBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(20, 16, 20, 18)
        b_layout.setSpacing(14)

        msg = QLabel(message)
        msg.setFont(QFont("DejaVu Sans Mono", 9))
        msg.setStyleSheet("color: #c8d4e0;")
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse)

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("ErrBtnOk")
        btn_ok.setFixedWidth(90)
        btn_ok.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)

        b_layout.addWidget(msg)
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QFrame#ErrHeader {
                background: rgba(30, 10, 10, 255);
                border-bottom: 1px solid rgba(200, 60, 60, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#ErrBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#ErrClose {
                background: transparent; border: none;
                color: #4a5a6a; font-size: 11px; border-radius: 5px;
            }
            QPushButton#ErrClose:hover {
                background: rgba(200,60,60,60); color: #ff8888;
            }
            QPushButton#ErrBtnOk {
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 8px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px; padding: 5px 0;
            }
            QPushButton#ErrBtnOk:hover {
                background: rgba(23, 147, 209, 70);
                border-color: rgba(35, 166, 255, 180);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


def _show_error(title: str, message: str, parent=None) -> None:
    _ErrorDialog(title, message, parent=parent).exec()


# ── Restore helpers ───────────────────────────────────────────────────────────

class _MaxLabel(QLabel):
    """Botão maximizar/restaurar com hover real."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self._set_normal()

    def _set_normal(self):
        self.setStyleSheet(
            "QLabel { color: #c8d4e0; font-size: 14px; "
            "border-radius: 6px; background: transparent; }"
        )
        self.setText("⬜")

    def _set_hover(self):
        self.setStyleSheet(
            "QLabel { color: #23a6ff; font-size: 14px; "
            "border-radius: 6px; background: rgba(35,166,255,30); }"
        )

    def enterEvent(self, event):
        self._set_hover()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_normal()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            win = self.window()
            if getattr(win, "_is_maximized", False):
                win.resize(win._normal_size)
                win.move(win._normal_pos)
                win._is_maximized = False
                self.setText("⬜")
            else:
                from PySide6.QtWidgets import QApplication
                win._normal_size = win.size()
                win._normal_pos = win.pos()
                screen = QApplication.primaryScreen().availableGeometry()
                win.resize(screen.width() - 40, screen.height() - 40)
                win.move(20, 20)
                win._is_maximized = True
                self.setText("❐")
        super().mousePressEvent(event)


class _CloseLabel(QLabel):
    """Label ✕ com hover real — QLabel:hover não funciona sem WA_Hover."""
    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setFixedSize(28, 28)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self._set_normal()

    def _set_normal(self):
        self.setStyleSheet(
            "QLabel { color: #c8d4e0; font-size: 14px; "
            "border-radius: 6px; background: transparent; }"
        )

    def _set_hover(self):
        self.setStyleSheet(
            "QLabel { color: #ff8888; font-size: 14px; "
            "border-radius: 6px; background: rgba(200,60,60,80); }"
        )

    def enterEvent(self, event):
        self._set_hover()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_normal()
        super().leaveEvent(event)


class _NavLabel(QLabel):
    """Botão de navegação (←) com hover real."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self._pixmap_normal = qta.icon("mdi6.arrow-left", color="#c8d4e0").pixmap(16, 16)
        self._pixmap_hover = qta.icon("mdi6.arrow-left", color="#23a6ff").pixmap(16, 16)
        self._set_normal()

    def _set_normal(self):
        self.setPixmap(self._pixmap_normal)
        self.setStyleSheet(
            "QLabel { background: rgba(10,15,25,200); border-radius: 6px; "
            "border: 1px solid rgba(31,92,255,80); }"
        )

    def _set_hover(self):
        self.setPixmap(self._pixmap_hover)
        self.setStyleSheet(
            "QLabel { background: rgba(23,147,209,70); border-radius: 6px; "
            "border: 1px solid rgba(35,166,255,180); }"
        )

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        if enabled:
            self._set_normal()
        else:
            self.setPixmap(qta.icon("mdi6.arrow-left", color="#3a4a5a").pixmap(16, 16))
            self.setStyleSheet(
                "QLabel { background: rgba(10,15,25,100); border-radius: 6px; "
                "border: 1px solid rgba(31,92,255,30); }"
            )

    def enterEvent(self, event):
        if self.isEnabled():
            self._set_hover()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.isEnabled():
            self._set_normal()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mousePressEvent(event)


class _RestoreDialog(QDialog):
    """Dialog de restore com 3 opções."""

    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle("Restore Snapshot")
        self.setModal(True)
        self.setFixedSize(880, 500)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("RstHeader")
        header.setFixedHeight(54)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 18, 0)

        icon = QLabel()
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.file-restore-outline", color="#c8d4e0").pixmap(20, 20))
        icon.setStyleSheet("QLabel { background: rgba(255,255,255,8); border-radius: 10px; }")

        lbl = QLabel("Restore Snapshot")
        lbl.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()

        h_layout.addWidget(icon)
        h_layout.addSpacing(12)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        body = QFrame()
        body.setObjectName("RstBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 20, 28, 22)
        b_layout.setSpacing(10)
        # Snapshot info — réplica completa do SnapshotCard (título, meta+size, last sync)
        snap_row = QHBoxLayout()
        snap_row.setSpacing(14)
        snap_row.setContentsMargins(0, 0, 0, 0)

        snap_icon = icon_badge(SNAPSHOT_GLYPH, 38)

        snap_text = QVBoxLayout()
        snap_text.setSpacing(4)
        snap_text.setContentsMargins(0, 0, 0, 0)

        snap_title = QLabel(self.entry.path.name)
        snap_title_font = QFont("DejaVu Sans Mono")
        snap_title_font.setPointSizeF(10.5)
        snap_title_font.setBold(True)
        snap_title.setFont(snap_title_font)
        snap_title.setStyleSheet("color: #ecf4ff;")

        snap_meta_row = QHBoxLayout()
        snap_meta_row.setSpacing(8)
        snap_meta_row.setContentsMargins(0, 0, 0, 0)

        snap_meta = QLabel(self.entry.meta_text)
        snap_meta.setFont(QFont("DejaVu Sans Mono", 10))
        snap_meta.setStyleSheet("color: #6b7a8d;")
        snap_meta_row.addWidget(snap_meta)

        if self.entry.size_str:
            snap_size_prefix = QLabel("snapshot size")
            snap_size_prefix.setFont(QFont("DejaVu Sans Mono", 9))
            snap_size_prefix.setStyleSheet("color: #6b7a8d;")
            snap_meta_row.addWidget(snap_size_prefix)

            snap_size_val = QLabel(self.entry.size_str)
            snap_size_val.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
            snap_size_val.setStyleSheet("color: #4ade80;")
            snap_meta_row.addWidget(snap_size_val)

        snap_meta_row.addStretch()

        snap_text.addWidget(snap_title)
        snap_text.addLayout(snap_meta_row)

        if self.entry.synced_at:
            snap_sync_row = QHBoxLayout()
            snap_sync_row.setSpacing(6)
            snap_sync_row.setContentsMargins(0, 0, 0, 0)

            snap_sync_icon = QLabel()
            snap_sync_icon.setPixmap(qta.icon(SYNC_GLYPH, color="#23a6ff").pixmap(14, 14))

            snap_sync_lbl = QLabel(f"last sync  {self.entry.synced_at}")
            snap_sync_lbl.setFont(QFont("DejaVu Sans Mono", 9))
            snap_sync_lbl.setStyleSheet("color: #23a6ff;")

            snap_sync_row.addWidget(snap_sync_icon)
            snap_sync_row.addWidget(snap_sync_lbl)
            snap_sync_row.addStretch()
            snap_text.addLayout(snap_sync_row)

        snap_row.addWidget(snap_icon)
        snap_row.addLayout(snap_text)
        snap_row.addStretch()
        lbl_choose = QLabel("Escolha o tipo de restore:")
        lbl_choose = QLabel("Escolha o tipo de restore:")
        lbl_choose.setFont(QFont("DejaVu Sans Mono", 9))
        lbl_choose.setStyleSheet("color: #9aa6b2;")
        btn1 = _RestoreOptionButton(
            glyph="mdi6.harddisk",
            title="Full System Restore",
            desc="Gera script bash para restaurar o sistema completo via live ISO (requer reboot).",
            color="#ff9966",
            parent=self,
        )
        btn1.clicked.connect(self._on_full_restore)

        btn2 = _RestoreOptionButton(
            glyph="mdi6.folder-search",
            title="File Browser",
            desc="Navega e restaura arquivos/pastas individuais do snapshot sem reboot.",
            color="#4ade80",
            parent=self,
        )
        btn2.clicked.connect(self._on_file_browser)

        btn3 = _RestoreOptionButton(
            glyph="mdi6.content-copy",
            title="Restore para disco alternativo",
            desc="Copia o snapshot inteiro para outro disco/partição montado.",
            color="#23a6ff",
            parent=self,
        )
        btn3.clicked.connect(self._on_alt_restore)

        b_layout.addLayout(snap_row)
        b_layout.addSpacing(16)
        b_layout.addWidget(lbl_choose)
        b_layout.addSpacing(10)
        b_layout.addWidget(btn1)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,10);")
        sep1.setFixedHeight(1)
        b_layout.addWidget(sep1)

        b_layout.addWidget(btn2)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,10);")
        sep2.setFixedHeight(1)
        b_layout.addWidget(sep2)

        b_layout.addWidget(btn3)
        b_layout.addStretch()

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #0d0f14;
                border-radius: 16px;
            }
            QFrame#RstHeader {
                background: rgba(255, 255, 255, 5);
                border-bottom: 1px solid rgba(255, 255, 255, 10);
                border-top-left-radius: 15px;
                border-top-right-radius: 15px;
            }
            QFrame#RstBody {
                background: #0d0f14;
                border-bottom-left-radius: 15px;
                border-bottom-right-radius: 15px;
            }
            QPushButton#RstClose {
                background: transparent; border: none;
                color: #6b7a8d; font-size: 13px; border-radius: 6px;
            }
            QPushButton#RstClose:hover {
                background: rgba(200,60,60,60); color: #ff8888;
            }
        """)

    def _on_full_restore(self) -> None:
        self.accept()
        _do_full_restore(self.entry, parent=self.parent())

    def _on_file_browser(self) -> None:
        self.accept()
        dlg = _FileBrowserDialog(self.entry, parent=self.parent())
        dlg.exec()

    def _on_alt_restore(self) -> None:
        self.accept()
        dlg = _AltRestoreDialog(self.entry, parent=self.parent())
        dlg.exec()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen, QColor, QBrush
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(255, 255, 255, 22))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 16, 16)


class _RestoreOptionButton(QFrame):
    clicked = Signal()

    def __init__(self, glyph: str, title: str, desc: str, color: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("RstOptionBtn")
        self.setFixedHeight(72)
        self._color = color
        self.setStyleSheet(f"""
            QFrame#RstOptionBtn {{
                background: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 10);
                border-radius: 12px;
            }}
            QFrame#RstOptionBtn:hover {{
                background: rgba(255, 255, 255, 9);
                border: 1px solid {color};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignVCenter)

        # Badge colorido via icon_badge
        ico_lbl = QLabel()
        ico_lbl.setFixedSize(36, 36)
        ico_lbl.setAlignment(Qt.AlignCenter)
        ico_lbl.setPixmap(qta.icon(glyph, color=color).pixmap(18, 18))
        h = color.lstrip("#")
        r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        ico_lbl.setStyleSheet(
            f"QLabel {{ background: rgba({r},{g},{b},40); "
            f"border-radius: 8px; border: 1px solid rgba({r},{g},{b},90); }}"
        )

        text = QVBoxLayout()
        text.setSpacing(1)
        text.setContentsMargins(0, 0, 0, 0)
        text.setAlignment(Qt.AlignVCenter)

        t = QLabel(title)
        t.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        t.setStyleSheet(f"color: {color}; background: transparent; border: none;")

        d = QLabel(desc)
        d.setFont(QFont("DejaVu Sans Mono", 9))
        d.setWordWrap(False)
        d.setStyleSheet("color: #6b7a8d; background: transparent; border: none;")

        text.addWidget(t)
        text.addWidget(d)
        layout.addWidget(ico_lbl, 0, Qt.AlignVCenter)
        layout.addLayout(text)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


def _do_full_restore(entry: SnapshotEntry, parent=None) -> None:
    try:
        meta_file = entry.path / "snapshot.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        destination_mountpoint = meta.get("destination_mountpoint", "")
        backup_root = Path(meta.get("backup_root", ""))

        root_path = str(entry.path) if entry.kind == "ROOT" else None
        home_candidate = backup_root / "HOME" / entry.path.name
        home_path = str(home_candidate) if home_candidate.exists() else None

        if entry.kind == "HOME":
            root_candidate = backup_root / "ROOT" / entry.path.name
            root_path = str(root_candidate) if root_candidate.exists() else None
            home_path = str(entry.path)

        output = Path(destination_mountpoint) / "carbonara-restore.sh"
        output_instr = Path(destination_mountpoint) / "carbonara-restore-INSTRUCOES.txt"
        project_root = Path(__file__).resolve().parents[3]
        python_bin = str(Path.home() / "venvs" / "pyside" / "bin" / "python3")

        # Detecta ISO sugerida para incluir nas instruções
        ventoy = Path("/mnt/VENTOY")
        suggested_iso = "sua-iso-arch.iso"
        try:
            isos = sorted(
                [p for p in ventoy.iterdir() if p.suffix.lower() == ".iso"],
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            arch_isos = [p.name for p in isos if "arch" in p.name.lower()]
            suggested_iso = arch_isos[0] if arch_isos else (isos[0].name if isos else suggested_iso)
        except Exception:
            pass

        script = f"""
import sys
sys.path.insert(0, {str(project_root)!r})
from core.snapshots.restore import generate_restore_script
from pathlib import Path
from datetime import datetime

script_path = generate_restore_script(
    snapshot_root_path={repr(root_path)},
    snapshot_home_path={repr(home_path)},
    output_path={str(output)!r},
)

# Gera arquivo de instruções junto
out_instr = Path({str(output_instr)!r})
content = f\"\"\"
================================================================================
  CARBONARA — INSTRUCOES DE RESTORE COMPLETO DO SISTEMA
  Gerado em: {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}
================================================================================

PASSO 1 — Boot pelo Ventoy
  Reinicie o computador e selecione pelo Ventoy:
  -> {suggested_iso}

PASSO 2 — Execute no shell do live ISO
  Cole o comando abaixo e pressione Enter:

  bash <(mount /dev/sdc3 /mnt/bk 2>/dev/null; cat /mnt/bk/carbonara-restore.sh)

  O script ira:
  OK Montar o disco de backup automaticamente
  OK Montar o array RAID0 (/dev/md127)
  OK Restaurar ROOT e HOME via rsync
  OK Reinstalar o GRUB (legacy BIOS)
  OK Desmontar tudo ao finalizar

PASSO 3 — Confirmacao
  Quando solicitado, digite exatamente:  RESTAURAR
  (qualquer outra entrada cancela a operacao)

================================================================================
  ARQUIVOS GERADOS
  Script:      {str(output)}
  Instrucoes:  {str(output_instr)}
================================================================================
\"\"\".strip()
out_instr.write_text(content, encoding="utf-8")
"""
        result = subprocess.run(
            [
                "pkexec", "env",
                f"DISPLAY={os.environ.get('DISPLAY', '')}",
                f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}",
                f"PYTHONPATH={project_root}",
                python_bin, "-c", script,
            ],
            capture_output=True, text=True,
        )

        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            _show_error("Restore", f"Erro ao gerar script:\n\n{err}", parent=parent)
            return

        dlg = _RestoreInstructionsDialog(str(output), str(output_instr), parent=parent)
        dlg.exec()

    except Exception as e:
        _show_error("Restore", f"Erro ao gerar script:\n\n{e}", parent=parent)


class _RestoreInstructionsDialog(QDialog):
    def __init__(self, script_path: str, instructions_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Script de Restore Gerado")
        self.setModal(True)
        self.setFixedSize(820, 520)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._instructions_path = instructions_path
        self._build_ui(script_path)
        self._apply_styles()

    def _generate_instructions(self, script_path: str) -> str:
        """Gera arquivo de instruções legível salvo junto ao script."""
        import re
        script_dir = Path(script_path).parent
        out = script_dir / "carbonara-restore-INSTRUCOES.txt"
        iso_names = [p.name for p in self._find_ventoy_isos()]
        arch_isos = [n for n in iso_names if "arch" in n.lower()]
        suggested_iso = arch_isos[0] if arch_isos else (iso_names[0] if iso_names else "sua-iso-arch.iso")

        content = f"""
================================================================================
  CARBONARA — INSTRUÇÕES DE RESTORE COMPLETO DO SISTEMA
  Gerado em: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
================================================================================

PASSO 1 — Boot pelo Ventoy
  Reinicie o computador e selecione pelo Ventoy:
  → {suggested_iso}

PASSO 2 — Execute no shell do live ISO
  Cole o comando abaixo e pressione Enter:

  bash <(mount /dev/sdc3 /mnt/bk 2>/dev/null; cat /mnt/bk/carbonara-restore.sh)

  O script irá:
  ✓ Montar o disco de backup automaticamente
  ✓ Montar o array RAID0 (/dev/md127)
  ✓ Restaurar ROOT e HOME via rsync
  ✓ Reinstalar o GRUB (legacy BIOS)
  ✓ Desmontar tudo ao finalizar

PASSO 3 — Confirmação
  Quando solicitado, digite exatamente:  RESTAURAR
  (qualquer outra entrada cancela a operação)

================================================================================
  ARQUIVOS GERADOS
  Script:      {script_path}
  Instruções:  {str(out)}
================================================================================
""".strip()

        try:
            out.write_text(content, encoding="utf-8")
        except Exception:
            pass
        return str(out)

    def _build_ui(self, script_path: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("RIHeader")
        header.setFixedHeight(48)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 16, 0)

        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.check-circle", color="#4ade80").pixmap(18, 18))
        icon.setStyleSheet("QLabel { background: rgba(74,222,128,30); border-radius: 8px; }")

        lbl = QLabel("Script de Restore Gerado")
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #4ade80;")

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()

        body = QFrame()
        body.setObjectName("RIBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 20, 28, 20)
        b_layout.setSpacing(6)

        # ── Passo 1: ISO disponível no Ventoy ────────────────────────────────
        lbl1 = QLabel("1.  Boot pelo Ventoy → selecione uma ISO Arch:")
        lbl1.setFont(QFont("DejaVu Sans Mono", 10))
        lbl1.setStyleSheet("color: #c8d4e0;")
        b_layout.addWidget(lbl1)

        isos = self._find_ventoy_isos()
        if isos:
            self.cmb_iso = QComboBox()
            self.cmb_iso.setFont(QFont("DejaVu Sans Mono", 10))
            for iso in isos:
                self.cmb_iso.addItem(iso.name)
            for i, iso in enumerate(isos):
                if "arch" in iso.name.lower():
                    self.cmb_iso.setCurrentIndex(i)
                    break
            self.cmb_iso.setStyleSheet("""
                QComboBox {
                    background: rgba(10,15,25,230);
                    border: 1px solid rgba(31,92,255,120);
                    border-radius: 6px; color: #ecf4ff;
                    font-family: "DejaVu Sans Mono"; font-size: 10px;
                    padding: 6px 12px;
                }
                QComboBox::drop-down { border: none; width: 20px; }
                QComboBox QAbstractItemView {
                    background: #0a0f19; color: #ecf4ff;
                    border: 1px solid rgba(31,92,255,140);
                }
            """)
            b_layout.addWidget(self.cmb_iso)
        else:
            lbl_no_iso = QLabel("⚠  Nenhuma ISO encontrada em /mnt/VENTOY")
            lbl_no_iso.setFont(QFont("DejaVu Sans Mono", 10))
            lbl_no_iso.setStyleSheet("color: #ff9966;")
            b_layout.addWidget(lbl_no_iso)

        b_layout.addSpacing(10)

        # ── Passo 2: Executar script ──────────────────────────────────────────
        lbl2 = QLabel("2.  No shell do live ISO, execute:")
        lbl2.setFont(QFont("DejaVu Sans Mono", 10))
        lbl2.setStyleSheet("color: #c8d4e0;")
        b_layout.addWidget(lbl2)

        cmd_lbl = QLabel("bash <(mount /dev/sdc3 /mnt/bk 2>/dev/null; cat /mnt/bk/carbonara-restore.sh)")
        cmd_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        cmd_lbl.setWordWrap(True)
        cmd_lbl.setStyleSheet(
            "color: #4ade80; background: rgba(74,222,128,15); "
            "border: 1px solid rgba(74,222,128,60); border-radius: 6px; padding: 10px 14px;"
        )
        cmd_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_layout.addWidget(cmd_lbl)

        b_layout.addSpacing(4)

        lbl3 = QLabel("O script monta os discos, restaura e reinstala o GRUB automaticamente.")
        lbl3.setFont(QFont("DejaVu Sans Mono", 9))
        lbl3.setStyleSheet("color: #6b7a8d;")
        lbl3.setWordWrap(True)
        b_layout.addWidget(lbl3)

        warn = QLabel("⚠  Confirme digitando RESTAURAR quando solicitado.")
        warn.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        warn.setStyleSheet("color: #ff9966;")
        b_layout.addWidget(warn)

        b_layout.addSpacing(14)

        # ── Arquivos gerados ──────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border: none; border-top: 1px solid rgba(31,92,255,40);")
        b_layout.addWidget(sep)

        b_layout.addSpacing(6)

        lbl_files = QLabel("Arquivos gerados em:")
        lbl_files.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        lbl_files.setStyleSheet("color: #c8d4e0;")
        b_layout.addWidget(lbl_files)

        lbl_script = QLabel(f"  Script:       {script_path}")
        lbl_script.setFont(QFont("DejaVu Sans Mono", 9))
        lbl_script.setStyleSheet("color: #9aa6b2;")
        lbl_script.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_layout.addWidget(lbl_script)

        lbl_instr = QLabel(f"  Instruções:   {self._instructions_path}")
        lbl_instr.setFont(QFont("DejaVu Sans Mono", 9))
        lbl_instr.setStyleSheet("color: #9aa6b2;")
        lbl_instr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_layout.addWidget(lbl_instr)

        b_layout.addStretch()

        btn_ok = QPushButton("Entendido")
        btn_ok.setObjectName("RIBtnOk")
        btn_ok.setFixedWidth(120)
        btn_ok.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _find_ventoy_isos(self) -> list:
        """Lista ISOs em /mnt/VENTOY ordenadas por data (mais recente primeiro)."""
        ventoy = Path("/mnt/VENTOY")
        if not ventoy.exists():
            return []
        try:
            return sorted(
                [p for p in ventoy.iterdir() if p.suffix.lower() == ".iso"],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            return []

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #080c14;
                border: 1px solid rgba(70, 188, 255, 220);
                border-radius: 14px;
            }
            QFrame#RIHeader {
                background: rgba(8, 20, 14, 255);
                border-bottom: 1px solid rgba(74, 222, 128, 80);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#RIBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#RIBtnOk {
                background: rgba(74, 222, 128, 180);
                border: 1px solid rgba(74, 222, 128, 220);
                border-radius: 8px; color: #08111d;
                font-family: "DejaVu Sans Mono";
                font-size: 11px; font-weight: 700; padding: 6px 0;
            }
            QPushButton#RIBtnOk:hover { background: rgba(94, 234, 149, 220); }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)




class _FileBrowserDialog(QDialog):
    """File browser para restaurar arquivos/pastas individuais do snapshot."""

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.snapshot_root = entry.path
        self.setWindowTitle("File Browser")
        self.setModal(True)
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowMaximizeButtonHint)
        self._current_path = self.snapshot_root
        self._selected_items = []
        self._conflict_mode = "overwrite"
        self._build_ui()
        self._apply_styles()
        self._populate_tree(self.snapshot_root)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("FBHeader")
        header.setFixedHeight(48)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 14, 0)
        hl.setSpacing(10)

        ico = QLabel()
        ico.setFixedSize(32, 32)
        ico.setAlignment(Qt.AlignCenter)
        ico.setPixmap(qta.icon("mdi6.folder-search", color="#4ade80").pixmap(22, 22))
        ico.setStyleSheet("QLabel { background: rgba(74,222,128,30); border-radius: 8px; }")

        lbl = QLabel("File Browser")
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        snap_lbl = QLabel(self.entry.path.name)
        snap_lbl.setFont(QFont("DejaVu Sans Mono", 8))
        snap_lbl.setStyleSheet("color: #6b7a8d;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()

        btn_max = _MaxLabel(self)

        hl.addWidget(ico)
        hl.addWidget(lbl)
        hl.addWidget(snap_lbl)
        hl.addStretch()
        hl.addWidget(btn_max)
        hl.addSpacing(4)
        hl.addWidget(btn_x)

        # Breadcrumb
        bc = QFrame()
        bc.setObjectName("FBBreadcrumb")
        bc.setFixedHeight(34)
        bcl = QHBoxLayout(bc)
        bcl.setContentsMargins(14, 0, 14, 0)
        bcl.setSpacing(6)

        self.btn_up = _NavLabel(self)
        self.btn_up.clicked.connect(self._go_up)
        self.btn_up.setEnabled(False)
        # Força reaplicação do estilo após o widget ser renderizado
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.btn_up.setEnabled(False))

        self.lbl_path = QLabel("/")
        self.lbl_path.setFont(QFont("DejaVu Sans Mono", 10))
        self.lbl_path.setStyleSheet("color: #9aa6b2;")

        bcl.addWidget(self.btn_up)
        bcl.addWidget(self.lbl_path, 1)

        # Corpo
        body = QFrame()
        body.setObjectName("FBBody")
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(12, 8, 12, 12)
        body_l.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background: rgba(31,92,255,40); }")

        # Árvore
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setObjectName("FBTree")
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setIconSize(QSize(24, 24))
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.setColumnCount(2)
        self.tree.header().hide()
        # Coluna 0 estica, coluna 1 (tamanho) largura fixa
        from PySide6.QtWidgets import QHeaderView
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.header().resizeSection(1, 80)

        # Painel direito
        right = QFrame()
        right.setObjectName("FBRight")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(8, 0, 0, 0)
        right_l.setSpacing(8)

        lbl_sel = QLabel("Selecionados para restore:")
        lbl_sel.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl_sel.setStyleSheet("color: #c8d4e0;")

        self.list_selected = QPlainTextEdit()
        self.list_selected.setReadOnly(True)
        self.list_selected.setObjectName("FBSelected")
        self.list_selected.setPlaceholderText("Nenhum item selecionado.\nSelecione arquivos/pastas na árvore.")

        # Conflito
        cf_frame = QFrame()
        cf_frame.setObjectName("FBConflict")
        cf_l = QVBoxLayout(cf_frame)
        cf_l.setContentsMargins(8, 8, 8, 8)
        cf_l.setSpacing(6)

        lbl_cf = QLabel("Se o arquivo já existir no sistema:")
        lbl_cf.setFont(QFont("DejaVu Sans Mono", 9))
        lbl_cf.setStyleSheet("color: #9aa6b2;")

        self.btn_overwrite = QPushButton("Sobrescrever")
        self.btn_overwrite.setObjectName("FBConflictBtn")
        self.btn_overwrite.setCheckable(True)
        self.btn_overwrite.setChecked(True)
        self.btn_overwrite.clicked.connect(lambda: self._set_conflict("overwrite"))

        self.btn_skip = QPushButton("Pular existentes")
        self.btn_skip.setObjectName("FBConflictBtn")
        self.btn_skip.setCheckable(True)
        self.btn_skip.clicked.connect(lambda: self._set_conflict("skip"))

        cf_l.addWidget(lbl_cf)
        cf_row = QHBoxLayout()
        cf_row.addWidget(self.btn_overwrite)
        cf_row.addWidget(self.btn_skip)
        cf_l.addLayout(cf_row)

        self.btn_restore = QPushButton("  Restaurar selecionados")
        self.btn_restore.setIcon(qta.icon("mdi6.file-restore-outline", color="#08111d"))
        self.btn_restore.setIconSize(QSize(16, 16))
        self.btn_restore.setObjectName("FBBtnRestore")
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self._on_restore)

        right_l.addWidget(lbl_sel)
        right_l.addWidget(self.list_selected, 1)
        right_l.addWidget(cf_frame)
        right_l.addWidget(self.btn_restore)

        splitter.addWidget(self.tree)
        splitter.addWidget(right)
        splitter.setSizes([520, 350])

        body_l.addWidget(splitter, 1)

        # Log
        self.log_frame = QFrame()
        self.log_frame.setObjectName("FBLogFrame")
        self.log_frame.setVisible(False)
        log_l = QVBoxLayout(self.log_frame)
        log_l.setContentsMargins(0, 0, 0, 0)
        log_l.setSpacing(4)

        self.restore_progress = QProgressBar()
        self.restore_progress.setRange(0, 0)
        self.restore_progress.setFixedHeight(4)
        self.restore_progress.setTextVisible(False)
        self.restore_progress.setObjectName("FBProgressBar")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("FBLog")
        self.log_view.setFixedHeight(100)

        log_l.addWidget(self.restore_progress)
        log_l.addWidget(self.log_view)
        body_l.addWidget(self.log_frame)

        root.addWidget(header)
        root.addWidget(bc)
        root.addWidget(body, 1)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #080c14;
                border: 1px solid rgba(31,92,255,80);
                border-radius: 14px;
            }
            QFrame#FBHeader {
                background: rgba(8,20,14,255);
                border-bottom: 1px solid rgba(74,222,128,80);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QFrame#FBBreadcrumb {
                background: rgba(6,9,16,200);
                border-bottom: 1px solid rgba(31,92,255,40);
            }
            QFrame#FBBody {
                background: #080c14;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QFrame#FBRight { background: transparent; }
            QFrame#FBConflict {
                background: rgba(10,15,25,180);
                border: 1px solid rgba(31,92,255,50);
                border-radius: 8px;
            }
            QFrame#FBLogFrame { background: transparent; }
            QPushButton#FBClose {
                background: transparent; border: none;
                color: #4a5a6a; font-size: 12px; border-radius: 6px;
            }
            QPushButton#FBClose:hover { background: rgba(200,60,60,60); color: #ff8888; }
            QPushButton#FBNavBtn {
                background: rgba(10,15,25,200);
                border: 1px solid rgba(31,92,255,80); border-radius: 6px;
            }
            QPushButton#FBNavBtn:hover {
                background: rgba(23,147,209,70);
                border-color: rgba(35,166,255,180);
            }
            QTreeWidget#FBTree {
                background: rgba(6,9,16,240);
                border: 1px solid rgba(31,92,255,55);
                border-radius: 8px; color: #c8d4e0;
                font-family: "DejaVu Sans Mono"; font-size: 12px; outline: none;
            }
            QTreeWidget#FBTree::item { padding: 6px 8px; border-radius: 4px; }
            QTreeWidget#FBTree::item:hover { background: rgba(35,166,255,30); }
            QTreeWidget#FBTree::item:selected { background: rgba(35,166,255,80); color: #ecf4ff; }
            QPlainTextEdit#FBSelected {
                background: rgba(6,9,16,200);
                border: 1px solid rgba(31,92,255,55); border-radius: 8px;
                color: #9aa6b2; font-family: "DejaVu Sans Mono";
                font-size: 11px; padding: 6px;
            }
            QPlainTextEdit#FBLog {
                background: rgba(6,9,16,200);
                border: 1px solid rgba(31,92,255,40); border-radius: 6px;
                color: #6b7a8d; font-family: "DejaVu Sans Mono";
                font-size: 9px; padding: 4px;
            }
            QPushButton#FBConflictBtn {
                background: rgba(10,15,25,200);
                border: 1px solid rgba(31,92,255,80); border-radius: 6px;
                color: #9aa6b2; font-family: "DejaVu Sans Mono";
                font-size: 11px; padding: 7px 12px;
            }
            QPushButton#FBConflictBtn:checked {
                background: rgba(35,166,255,100);
                border-color: rgba(35,166,255,200); color: #ecf4ff;
            }
            QPushButton#FBBtnRestore {
                background: rgba(74,222,128,180);
                border: 1px solid rgba(74,222,128,220);
                border-radius: 8px; color: #08111d;
                font-family: "DejaVu Sans Mono"; font-size: 13px;
                font-weight: 700; padding: 10px 0;
            }
            QPushButton#FBBtnRestore:hover { background: rgba(94,234,149,220); }
            QPushButton#FBBtnRestore:disabled {
                background: rgba(30,40,30,180);
                border-color: rgba(74,222,128,40); color: #3a4a3a;
            }
            QProgressBar#FBProgressBar {
                background: rgba(31,92,255,20); border: none; border-radius: 2px;
            }
            QProgressBar#FBProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 rgba(74,222,128,200), stop:1 rgba(35,166,255,200));
                border-radius: 2px;
            }
        """)

    def _populate_tree(self, path):
        self.tree.clear()
        self._current_path = path
        try:
            rel = path.relative_to(self.snapshot_root)
            display = "/" + str(rel) if str(rel) != "." else "/"
        except ValueError:
            display = str(path)
        self.lbl_path.setText(display)
        self.btn_up.setEnabled(path != self.snapshot_root)

        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            if entry.name == "snapshot.json":
                continue
            item = self._make_item(entry)
            self.tree.addTopLevelItem(item)
            # Adiciona filho sentinel para pastas não vazias
            if entry.is_dir() and not entry.is_symlink():
                self._add_sentinel_if_needed(item, entry)

    def _make_item(self, entry: Path) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(0, entry.name)
        item.setData(0, Qt.UserRole, entry)
        item.setData(0, Qt.UserRole + 1, False)  # loaded = False
        if entry.is_symlink():
            item.setIcon(0, qta.icon("mdi6.link-variant", color="#9aa6b2"))
        elif entry.is_dir():
            item.setIcon(0, qta.icon("mdi6.folder", color="#23a6ff"))
        else:
            item.setIcon(0, self._file_icon(entry))
            try:
                item.setText(1, self._fmt_size(entry.stat().st_size))
            except OSError:
                pass
        return item

    def _add_sentinel_if_needed(self, item: QTreeWidgetItem, path: Path) -> None:
        """Adiciona filho placeholder se a pasta tiver conteúdo."""
        try:
            has_children = any(
                e for e in path.iterdir() if e.name != "snapshot.json"
            )
            if has_children:
                sentinel = QTreeWidgetItem()
                sentinel.setText(0, "carregando...")
                sentinel.setData(0, Qt.UserRole, None)  # marca sentinel
                sentinel.setDisabled(True)
                item.addChild(sentinel)
        except PermissionError:
            pass

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Popula filhos de uma pasta quando expandida (lazy loading)."""
        already_loaded = item.data(0, Qt.UserRole + 1)
        if already_loaded:
            return

        path: Path = item.data(0, Qt.UserRole)
        if not path or not path.is_dir():
            return

        # Remove sentinel
        item.takeChildren()

        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            if entry.name == "snapshot.json":
                continue
            child = self._make_item(entry)
            item.addChild(child)
            if entry.is_dir() and not entry.is_symlink():
                self._add_sentinel_if_needed(child, entry)

        item.setData(0, Qt.UserRole + 1, True)  # loaded = True

    def _file_icon(self, path):
        ext = path.suffix.lower()
        m = {
            ".py": ("mdi6.language-python", "#4ade80"),
            ".sh": ("mdi6.console", "#4ade80"),
            ".conf": ("mdi6.cog", "#9aa6b2"),
            ".json": ("mdi6.code-json", "#ff9966"),
            ".log": ("mdi6.text-box-outline", "#6b7a8d"),
            ".service": ("mdi6.cog-outline", "#9aa6b2"),
        }
        g, c = m.get(ext, ("mdi6.file-outline", "#6b7a8d"))
        return qta.icon(g, color=c)

    def _fmt_size(self, size):
        if size >= 1024**3: return f"{size/1024**3:.1f} GB"
        if size >= 1024**2: return f"{size/1024**2:.1f} MB"
        if size >= 1024: return f"{size/1024:.0f} KB"
        return f"{size} B"

    def _go_up(self):
        if self._current_path != self.snapshot_root:
            self._populate_tree(self._current_path.parent)

    def _on_double_click(self, item, col):
        path = item.data(0, Qt.UserRole)
        if path and path.is_dir() and not path.is_symlink():
            self._populate_tree(path)

    def _on_selection_changed(self):
        paths = [
            item.data(0, Qt.UserRole)
            for item in self.tree.selectedItems()
            if item.data(0, Qt.UserRole)
        ]
        self._selected_items = paths
        if paths:
            self.list_selected.setPlainText(
                "\n".join(str(p.relative_to(self.snapshot_root)) for p in paths)
            )
        else:
            self.list_selected.clear()
        self.btn_restore.setEnabled(bool(paths))

    def _set_conflict(self, mode):
        self._conflict_mode = mode
        self.btn_overwrite.setChecked(mode == "overwrite")
        self.btn_skip.setChecked(mode == "skip")

    def _on_restore(self):
        if not self._selected_items:
            return
        confirm = _ConfirmRestoreDialog(
            f"{len(self._selected_items)} item(ns)",
            self._conflict_mode, parent=self
        )
        if confirm.exec() != QDialog.Accepted:
            return

        items_repr = repr([str(p) for p in self._selected_items])
        snap_root_repr = repr(str(self.snapshot_root))
        conflict_repr = repr(self._conflict_mode)
        # Snapshot HOME armazena o conteúdo de /home/ sem o prefixo "home/"
        # — precisa recolocar esse prefixo no destino real.
        dest_prefix_repr = repr("home") if self.entry.kind.upper() == "HOME" else repr("")

        script = f"""
import shutil
from pathlib import Path

snapshot_root = Path({snap_root_repr})
items = {items_repr}
conflict = {conflict_repr}
dest_prefix = {dest_prefix_repr}

def to_dest(rel: Path) -> Path:
    if dest_prefix:
        return Path("/") / dest_prefix / rel
    return Path("/") / rel

for src_str in items:
    src = Path(src_str)
    try:
        rel = src.relative_to(snapshot_root)
    except ValueError:
        continue
    dst = to_dest(rel)
    if src.is_dir():
        for f in src.rglob("*"):
            if f.is_file() or f.is_symlink():
                try:
                    rel_f = f.relative_to(snapshot_root)
                    dst_f = to_dest(rel_f)
                    if dst_f.exists() and conflict == "skip":
                        print(f"SKIP: {{dst_f}}")
                        continue
                    dst_f.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst_f)
                    print(f"OK: {{dst_f}}")
                except Exception as ex:
                    print(f"ERR: {{dst_f}} -- {{ex}}")
    else:
        try:
            if dst.exists() and conflict == "skip":
                print(f"SKIP: {{dst}}")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"OK: {{dst}}")
        except Exception as ex:
            print(f"ERR: {{dst}} -- {{ex}}")
"""
        project_root = Path(__file__).resolve().parents[3]
        python_bin = str(Path.home() / "venvs" / "pyside" / "bin" / "python3")

        self.log_frame.setVisible(True)
        self.log_view.clear()
        self.btn_restore.setEnabled(False)
        self.restore_progress.setRange(0, 0)

        worker = _FileBrowserRestoreWorker(
            python_bin=python_bin,
            project_root=str(project_root),
            script=script,
            parent=self,
        )
        worker.log_line.connect(self._on_log_line)
        worker.finished_ok.connect(self._on_restore_done)
        worker.failed.connect(self._on_restore_fail)
        self._restore_worker = worker
        worker.start()

    def _on_log_line(self, line):
        self.log_view.appendPlainText(line)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def _on_restore_done(self):
        self.restore_progress.setRange(0, 1)
        self.restore_progress.setValue(1)
        self.btn_restore.setEnabled(True)
        self._on_log_line("─── Restore concluído ───")

    def _on_restore_fail(self, msg):
        self.restore_progress.setRange(0, 1)
        self.restore_progress.setValue(0)
        self.btn_restore.setEnabled(True)
        self._on_log_line(f"ERRO: {msg}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(event.globalPosition().toPoint() - self._drag)


class _ConfirmRestoreDialog(QDialog):
    def __init__(self, label, conflict, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setFixedSize(440, 180)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("CRHeader")
        header.setFixedHeight(44)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 14, 0)
        ico = QLabel()
        ico.setFixedSize(24, 24)
        ico.setAlignment(Qt.AlignCenter)
        ico.setPixmap(qta.icon("mdi6.file-restore-outline", color="#4ade80").pixmap(16, 16))
        ico.setStyleSheet("QLabel { background: rgba(74,222,128,30); border-radius: 6px; }")
        lbl = QLabel("Confirmar Restore")
        lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")
        hl.addWidget(ico)
        hl.addSpacing(8)
        hl.addWidget(lbl)
        hl.addStretch()

        body = QFrame()
        body.setObjectName("CRBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 14, 20, 16)
        bl.setSpacing(12)

        ct = "sobrescrevendo existentes" if conflict == "overwrite" else "pulando existentes"
        msg = QLabel(f"Restaurar {label} para o sistema,\n{ct}?")
        msg.setFont(QFont("DejaVu Sans Mono", 9))
        msg.setStyleSheet("color: #c8d4e0;")

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("CRBtnCancel")
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Restaurar")
        btn_ok.setObjectName("CRBtnOk")
        btn_ok.setFixedWidth(100)
        btn_ok.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        bl.addWidget(msg)
        bl.addLayout(btn_row)
        root.addWidget(header)
        root.addWidget(body, 1)

        self.setStyleSheet("""
            QFrame#CRHeader {
                background: rgba(8,20,14,255);
                border-bottom: 1px solid rgba(74,222,128,80);
                border-top-left-radius: 10px; border-top-right-radius: 10px;
            }
            QFrame#CRBody {
                background: #080c14;
                border-bottom-left-radius: 10px; border-bottom-right-radius: 10px;
            }
            QPushButton#CRBtnCancel {
                background: rgba(10,15,25,230); border: 1px solid rgba(31,92,255,120);
                border-radius: 7px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono"; font-size: 10px; padding: 5px 0;
            }
            QPushButton#CRBtnCancel:hover { background: rgba(23,147,209,70); }
            QPushButton#CRBtnOk {
                background: rgba(74,222,128,180); border: 1px solid rgba(74,222,128,220);
                border-radius: 7px; color: #08111d;
                font-family: "DejaVu Sans Mono"; font-size: 10px;
                font-weight: 700; padding: 5px 0;
            }
            QPushButton#CRBtnOk:hover { background: rgba(94,234,149,220); }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(event.globalPosition().toPoint() - self._drag)


class _FileBrowserRestoreWorker(QThread):
    log_line = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, python_bin, project_root, script, parent=None):
        super().__init__(parent)
        self._python_bin = python_bin
        self._project_root = project_root
        self._script = script

    def run(self):
        try:
            result = subprocess.run(
                [
                    "pkexec", "env",
                    f"DISPLAY={os.environ.get('DISPLAY', '')}",
                    f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}",
                    f"PYTHONPATH={self._project_root}",
                    self._python_bin, "-c", self._script,
                ],
                capture_output=True, text=True,
            )
            for line in result.stdout.splitlines():
                if line.strip():
                    self.log_line.emit(line)
            if result.returncode != 0:
                err = result.stderr.strip() or f"exit code {result.returncode}"
                self.failed.emit(err)
            else:
                self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))



# ── Alt Restore helpers ───────────────────────────────────────────────────────

class _AltRestoreDialog(QDialog):
    """Dialog para restaurar snapshot para um disco alternativo."""

    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle("Restore para disco alternativo")
        self.setModal(True)
        self.setFixedSize(680, 420)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._destinations = []
        self._build_ui()
        self._apply_styles()
        self._load_destinations()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("ARHeader")
        header.setFixedHeight(52)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 0, 16, 0)

        ico = QLabel()
        ico.setFixedSize(32, 32)
        ico.setAlignment(Qt.AlignCenter)
        ico.setPixmap(qta.icon("mdi6.content-copy", color="#23a6ff").pixmap(20, 20))
        ico.setStyleSheet("QLabel { background: rgba(35,166,255,40); border-radius: 9px; }")

        lbl = QLabel("Restore para disco alternativo")
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()

        hl.addWidget(ico)
        hl.addSpacing(10)
        hl.addWidget(lbl)
        hl.addStretch()
        hl.addWidget(btn_x)

        # Body
        body = QFrame()
        body.setObjectName("ARBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 18, 24, 20)
        bl.setSpacing(12)

        # Snapshot info
        snap_lbl = QLabel(self.entry.path.name)
        snap_lbl.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        snap_lbl.setStyleSheet(
            "color: #23a6ff; background: rgba(35,166,255,20); "
            "border: 1px solid rgba(35,166,255,60); border-radius: 6px; padding: 4px 10px;"
        )

        # Destino
        lbl_dest = QLabel("Selecione o disco de destino:")
        lbl_dest.setFont(QFont("DejaVu Sans Mono", 10))
        lbl_dest.setStyleSheet("color: #c8d4e0;")

        self.cmb_dest = QComboBox()
        self.cmb_dest.setFont(QFont("DejaVu Sans Mono", 10))
        self.cmb_dest.setMinimumHeight(36)
        style_combo_popup(self.cmb_dest)

        # Opções de cópia
        lbl_opts = QLabel("Opções:")
        lbl_opts.setFont(QFont("DejaVu Sans Mono", 10))
        lbl_opts.setStyleSheet("color: #c8d4e0;")

        opts_row = QHBoxLayout()
        opts_row.setSpacing(10)

        self.chk_delete = QPushButton("Sincronizar (--delete)")
        self.chk_delete.setCheckable(True)
        self.chk_delete.setChecked(False)
        self.chk_delete.setObjectName("AROptBtn")

        self.chk_hardlinks = QPushButton("Preservar hard-links (-H)")
        self.chk_hardlinks.setCheckable(True)
        self.chk_hardlinks.setChecked(True)
        self.chk_hardlinks.setObjectName("AROptBtn")

        opts_row.addWidget(self.chk_delete)
        opts_row.addWidget(self.chk_hardlinks)
        opts_row.addStretch()

        # Info destino
        self.lbl_dest_info = QLabel("—")
        self.lbl_dest_info.setFont(QFont("DejaVu Sans Mono", 9))
        self.lbl_dest_info.setStyleSheet("color: #6b7a8d;")
        self.cmb_dest.currentIndexChanged.connect(self._on_dest_changed)

        # Warn
        warn = QLabel("⚠  O conteúdo existente no destino pode ser alterado.")
        warn.setFont(QFont("DejaVu Sans Mono", 8))
        warn.setStyleSheet("color: #ff9966;")

        # Botões
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("ARBtnCancel")
        btn_cancel.setFixedWidth(110)
        btn_cancel.clicked.connect(self.reject)

        self.btn_start = QPushButton("Iniciar Restore")
        self.btn_start.setObjectName("ARBtnStart")
        self.btn_start.setFixedWidth(140)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_start)

        bl.addWidget(snap_lbl)
        bl.addWidget(lbl_dest)
        bl.addWidget(self.cmb_dest)
        bl.addWidget(self.lbl_dest_info)
        bl.addWidget(lbl_opts)
        bl.addLayout(opts_row)
        bl.addStretch()
        bl.addWidget(warn)
        bl.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #080c14;
                border-radius: 14px;
            }
            QFrame#ARHeader {
                background: rgba(8, 20, 40, 255);
                border-bottom: 1px solid rgba(35, 166, 255, 80);
                border-top-left-radius: 13px;
                border-top-right-radius: 13px;
            }
            QFrame#ARBody {
                background: #080c14;
                border-bottom-left-radius: 13px;
                border-bottom-right-radius: 13px;
            }
            QComboBox {
                background: rgba(10,15,25,230);
                border: 1px solid rgba(31,92,255,120);
                border-radius: 8px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono"; padding: 6px 12px;
            }
            QComboBox:hover { border-color: rgba(35,166,255,200); }
            QComboBox::drop-down { border: none; width: 24px; }
            QPushButton#AROptBtn {
                background: rgba(10,15,25,200);
                border: 1px solid rgba(31,92,255,80);
                border-radius: 8px; color: #9aa6b2;
                font-family: "DejaVu Sans Mono"; font-size: 9px;
                padding: 5px 12px;
            }
            QPushButton#AROptBtn:checked {
                background: rgba(35,166,255,100);
                border-color: rgba(35,166,255,200); color: #ecf4ff;
            }
            QPushButton#ARBtnCancel {
                background: rgba(10,15,25,230);
                border: 1px solid rgba(31,92,255,120);
                border-radius: 8px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono"; font-size: 11px;
                padding: 6px 0;
            }
            QPushButton#ARBtnCancel:hover {
                background: rgba(23,147,209,70);
                border-color: rgba(35,166,255,180);
            }
            QPushButton#ARBtnStart {
                background: rgba(35,166,255,180);
                border: 1px solid rgba(35,166,255,220);
                border-radius: 8px; color: #08111d;
                font-family: "DejaVu Sans Mono"; font-size: 11px;
                font-weight: 700; padding: 6px 0;
            }
            QPushButton#ARBtnStart:hover { background: rgba(70,188,255,220); }
            QPushButton#ARBtnStart:disabled {
                background: rgba(10,15,25,100);
                border-color: rgba(31,92,255,30); color: #3a4a5a;
            }
        """)

    def _load_destinations(self):
        """Lista discos montados excluindo o disco de origem do snapshot."""
        snap_mount = None
        try:
            meta = json.loads((self.entry.path / "snapshot.json").read_text())
            snap_mount = meta.get("destination_mountpoint", "")
        except Exception:
            pass

        self.cmb_dest.clear()
        self._destinations = []

        for dest in list_backup_destinations():
            if dest.mountpoint == snap_mount:
                continue  # exclui o disco onde o snapshot está
            self._destinations.append(dest)
            label = f"{dest.label}  •  {format_gb(dest.free_gb)} livre  •  {dest.mountpoint}"
            self.cmb_dest.addItem(label, dest)

        self.btn_start.setEnabled(bool(self._destinations))
        if not self._destinations:
            self.lbl_dest_info.setText("Nenhum disco alternativo disponível.")
        else:
            self._on_dest_changed(0)

    def _on_dest_changed(self, index: int):
        if index < 0 or index >= len(self._destinations):
            return
        dest = self._destinations[index]
        self.lbl_dest_info.setText(
            f"{format_gb(dest.free_gb)} livre de {format_gb(dest.total_gb)} "
            f"• {dest.fs_type}"
        )

    def _on_start(self):
        idx = self.cmb_dest.currentIndex()
        if idx < 0 or idx >= len(self._destinations):
            return
        dest = self._destinations[idx]

        use_delete = self.chk_delete.isChecked()
        use_hardlinks = self.chk_hardlinks.isChecked()

        self.accept()

        project_root = Path(__file__).resolve().parents[3]
        python_bin = str(Path.home() / "venvs" / "pyside" / "bin" / "python3")
        snap_path = str(self.entry.path)
        dest_path = dest.mountpoint

        script = f"""
import sys, subprocess
sys.path.insert(0, {str(project_root)!r})

from PySide6.QtWidgets import QApplication
from ui.widgets.backup_progress import BackupProgressDialog
from core.workers.rsync_worker import RsyncWorker
from pathlib import Path

snap = Path({snap_path!r})
dest_base = Path({dest_path!r}) / "CarbonaraSnapshots" / snap.parent.name
dest_base.mkdir(parents=True, exist_ok=True)
dest_dir = dest_base / snap.name

cmd = [
    "rsync", "-aAXHh",
    "--numeric-ids",
    "--info=progress2",
    "--out-format=Copiando: %n",
]
{"""cmd.append("--delete")""" if use_delete else ""}
{"""cmd.append("-H")""" if use_hardlinks else ""}
cmd += [str(snap) + "/", str(dest_dir) + "/"]

app = QApplication([])
dialog = BackupProgressDialog("Restore para {dest.label}")
dialog.set_running(True)
dialog.set_status("Iniciando restore...")
dialog.progress.setRange(0, 100)
dialog.progress.setValue(0)

worker = RsyncWorker(cmd, title="Copiando snapshot...", parent=dialog)
dialog.register_worker(worker)
worker.progress_changed.connect(dialog.progress.setValue)
worker.status_changed.connect(dialog.set_status)
worker.file_changed.connect(dialog.set_current_file)
worker.log_line.connect(dialog.append_log)

def on_ok():
    dialog.set_status("Restore concluído com sucesso.")
    dialog.progress.setValue(100)
    dialog.set_running(False)
    dialog.btn_close.setEnabled(True)

def on_fail(msg):
    dialog.set_status(f"Erro: {{msg}}")
    dialog.set_running(False)
    dialog.btn_close.setEnabled(True)

worker.finished_ok.connect(on_ok)
worker.failed.connect(on_fail)
worker.start()
dialog.exec()
"""
        cmd_pkexec = [
            "pkexec", "env",
            f"DISPLAY={os.environ.get('DISPLAY', '')}",
            f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}",
            f"PYTHONPATH={project_root}",
            python_bin, "-c", script,
        ]

        try:
            subprocess.Popen(cmd_pkexec, cwd=str(project_root))
        except Exception as e:
            _show_error("Restore Alternativo", str(e), parent=self.parent())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(event.globalPosition().toPoint() - self._drag)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen, QColor
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(31, 141, 218, 120))
        pen.setWidth(1)
        painter.setPen(pen)
        from PySide6.QtCore import Qt as _Qt
        painter.setBrush(_Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 14, 14)

# ── Sync helpers ─────────────────────────────────────────────────────────────

class _SyncConfirmDialog(QDialog):
    """Dialog de confirmação estilizado para sync de snapshot."""

    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirmar sincronização")
        self.setModal(True)
        self.setFixedSize(520, 220)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(entry)
        self._apply_styles()

    def _build_ui(self, entry: SnapshotEntry) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("SyncHeader")
        header.setFixedHeight(48)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 16, 0)

        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.sync", color="#23a6ff").pixmap(18, 18))
        icon.setStyleSheet("QLabel { background: rgba(35,166,255,40); border-radius: 8px; }")

        lbl = QLabel("Sincronizar Snapshot")
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        body = QFrame()
        body.setObjectName("SyncBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 18, 24, 20)
        b_layout.setSpacing(10)

        warn = QLabel("O snapshot será atualizado com o estado atual do sistema. Apenas arquivos modificados serão transferidos.")
        warn.setWordWrap(True)
        warn.setFont(QFont("DejaVu Sans Mono", 9))
        warn.setStyleSheet("color: #c8d4e0;")

        snap_label = QLabel(entry.path.name)
        snap_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        snap_label.setStyleSheet(
            "color: #23a6ff; background: rgba(35,166,255,20); "
            "border: 1px solid rgba(35,166,255,60); border-radius: 6px; padding: 4px 10px;"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("SyncBtnCancel")
        btn_cancel.setFixedWidth(110)
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton("Sincronizar")
        btn_confirm.setObjectName("SyncBtnConfirm")
        btn_confirm.setFixedWidth(120)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)

        b_layout.addWidget(warn)
        b_layout.addWidget(snap_label)
        b_layout.addStretch()
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QFrame#SyncHeader {
                background: rgba(8, 20, 40, 255);
                border-bottom: 1px solid rgba(35, 166, 255, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#SyncBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#SyncClose {
                background: transparent;
                border: none;
                color: #4a5a6a;
                font-size: 12px;
                border-radius: 6px;
            }
            QPushButton#SyncClose:hover {
                background: rgba(200, 60, 60, 60);
                color: #ff8888;
            }
            QPushButton#SyncBtnCancel {
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 8px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                padding: 6px 0;
            }
            QPushButton#SyncBtnCancel:hover {
                background: rgba(23, 147, 209, 70);
                border-color: rgba(35, 166, 255, 180);
            }
            QPushButton#SyncBtnConfirm {
                background: rgba(31, 92, 255, 180);
                border: 1px solid rgba(35, 166, 255, 200);
                border-radius: 8px;
                color: #ffffff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: 700;
                padding: 6px 0;
            }
            QPushButton#SyncBtnConfirm:hover {
                background: rgba(35, 166, 255, 220);
                border-color: rgba(70, 188, 255, 255);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


# ── Delete helpers ────────────────────────────────────────────────────────────

class _DeleteConfirmDialog(QDialog):
    """Dialog de confirmação estilizado para delete de snapshot."""

    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirmar exclusão")
        self.setModal(True)
        self.setFixedSize(520, 220)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(entry)
        self._apply_styles()

    def _build_ui(self, entry: SnapshotEntry) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("DelHeader")
        header.setFixedHeight(48)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 16, 0)

        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignCenter)
        import qtawesome as qta
        icon.setPixmap(qta.icon("mdi6.delete", color="#ff6666").pixmap(18, 18))
        icon.setStyleSheet("QLabel { background: rgba(200,60,60,40); border-radius: 8px; }")

        lbl = QLabel("Excluir Snapshot")
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()



        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        # Body
        body = QFrame()
        body.setObjectName("DelBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 18, 24, 20)
        b_layout.setSpacing(10)

        warn = QLabel("Esta ação é irreversível. O snapshot será permanentemente removido do disco.")
        warn.setWordWrap(True)
        warn.setFont(QFont("DejaVu Sans Mono", 9))
        warn.setStyleSheet("color: #c8d4e0;")

        snap_label = QLabel(entry.path.name)
        snap_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        snap_label.setStyleSheet(
            "color: #ff9966; background: rgba(200,60,60,20); "
            "border: 1px solid rgba(200,60,60,60); border-radius: 6px; padding: 4px 10px;"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("DelBtnCancel")
        btn_cancel.setFixedWidth(110)
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton("Excluir")
        btn_confirm.setObjectName("DelBtnConfirm")
        btn_confirm.setFixedWidth(110)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)

        b_layout.addWidget(warn)
        b_layout.addWidget(snap_label)
        b_layout.addStretch()
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QFrame#DelHeader {
                background: rgba(30, 10, 10, 255);
                border-bottom: 1px solid rgba(200, 60, 60, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#DelBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#DelClose {
                background: transparent;
                border: none;
                color: #4a5a6a;
                font-size: 12px;
                border-radius: 6px;
            }
            QPushButton#DelClose:hover {
                background: rgba(200, 60, 60, 60);
                color: #ff8888;
            }
            QPushButton#DelBtnCancel {
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 8px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                padding: 6px 0;
            }
            QPushButton#DelBtnCancel:hover {
                background: rgba(23, 147, 209, 70);
                border-color: rgba(35, 166, 255, 180);
            }
            QPushButton#DelBtnConfirm {
                background: rgba(180, 40, 40, 180);
                border: 1px solid rgba(255, 80, 80, 160);
                border-radius: 8px;
                color: #ffffff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: 700;
                padding: 6px 0;
            }
            QPushButton#DelBtnConfirm:hover {
                background: rgba(220, 60, 60, 220);
                border-color: rgba(255, 120, 120, 220);
            }
        """)

    # Drag
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


class _DeleteProgressDialog(QDialog):
    """Loader exibido enquanto o snapshot está sendo removido."""

    def __init__(self, snap_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Removendo snapshot")
        self.setModal(True)
        self.setFixedSize(420, 160)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._dots = 0
        self._build_ui(snap_name)
        self._apply_styles()

        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _build_ui(self, snap_name: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("DPHeader")
        header.setFixedHeight(46)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 18, 0)

        import qtawesome as qta
        icon = QLabel()
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.delete", color="#ff6666").pixmap(16, 16))
        icon.setStyleSheet("QLabel { background: rgba(200,60,60,40); border-radius: 7px; }")

        lbl = QLabel("Removendo Snapshot")
        lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()

        # Body
        body = QFrame()
        body.setObjectName("DPBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 16, 24, 20)
        b_layout.setSpacing(10)

        self.lbl_status = QLabel("Aguardando autenticação...")
        self.lbl_status.setFont(QFont("DejaVu Sans Mono", 10))
        self.lbl_status.setStyleSheet("color: #c8d4e0;")
        self.lbl_status.setAlignment(Qt.AlignCenter)

        snap_lbl = QLabel(snap_name)
        snap_lbl.setFont(QFont("DejaVu Sans Mono", 9))
        snap_lbl.setStyleSheet("color: #6b7a8d;")
        snap_lbl.setAlignment(Qt.AlignCenter)

        # Barra indeterminada slim
        from PySide6.QtWidgets import QProgressBar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # modo indeterminado — pulsa
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setObjectName("DPBar")

        b_layout.addWidget(self.lbl_status)
        b_layout.addWidget(snap_lbl)
        b_layout.addSpacing(4)
        b_layout.addWidget(self.progress)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QFrame#DPHeader {
                background: rgba(30, 10, 10, 255);
                border-bottom: 1px solid rgba(200, 60, 60, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#DPBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QProgressBar#DPBar {
                background: rgba(31, 92, 255, 20);
                border: none;
                border-radius: 2px;
            }
            QProgressBar#DPBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(31, 92, 255, 220),
                    stop:1 rgba(35, 166, 255, 220)
                );
                border-radius: 2px;
            }
        """)

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % 4
        dots = "." * self._dots
        self.lbl_status.setText(f"Removendo{dots}")

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)

    # Drag
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


class _DeleteWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, snapshot_path: Path, parent=None):
        super().__init__(parent)
        self._path = snapshot_path

    def run(self) -> None:
        try:
            kind_base = self._path.parent
            link = kind_base / "latest"

            # Verifica se este snapshot é o apontado pelo latest
            is_latest = False
            try:
                if link.is_symlink():
                    resolved = (kind_base / link.readlink()).resolve()
                    is_latest = resolved == self._path.resolve()
            except Exception:
                pass

            # Calcula qual será o novo latest antes de deletar
            new_latest: Path | None = None
            if is_latest:
                candidates = sorted(
                    [p for p in kind_base.iterdir()
                     if p.is_dir() and p.name != "latest" and p != self._path],
                    key=lambda p: p.name,
                )
                new_latest = candidates[-1] if candidates else None

            # Script python que roda como root via pkexec
            script = f"""
import shutil, os
from pathlib import Path

target = Path({str(self._path)!r})
link   = Path({str(link)!r})

shutil.rmtree(target)

# Atualiza symlink latest
if link.is_symlink() or link.exists():
    link.unlink()

new_latest = {repr(str(new_latest)) if new_latest else repr(None)}
if new_latest:
    link.symlink_to(Path(new_latest).name)
"""
            import subprocess
            from pathlib import Path as _Path

            python_bin = str(_Path.home() / "venvs" / "pyside" / "bin" / "python3")

            result = subprocess.run(
                ["pkexec", python_bin, "-c", script],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                err = result.stderr.strip() or f"exit code {result.returncode}"
                self.failed.emit(err)
                return

            self.finished_ok.emit(f"Snapshot {self._path.name} removido com sucesso.")

        except Exception as exc:
            self.failed.emit(str(exc))
