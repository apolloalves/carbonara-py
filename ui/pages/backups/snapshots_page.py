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
from PySide6.QtCore import Qt, QTimer, Signal, QSize
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
INTEGRITY_GLYPH = "mdi6.shield-check"
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

                meta_text = f"{created_at} • {status}"
                if source:
                    meta_text = f"{meta_text} • {source}"

                entries.append(
                    SnapshotEntry(
                        kind=kind_dir.name,
                        path=snap,
                        meta_text=meta_text,
                        modified_text=datetime.fromtimestamp(
                            stat.st_mtime
                        ).strftime("%Y-%m-%d %H:%M:%S"),
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
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 12px;
                color: #ecf4ff;
                font: 700 10pt "DejaVu Sans Mono";
                padding: 0px 12px;
            }

            QPushButton:hover {
                background: rgba(35, 166, 255, 160);
                border: 1px solid rgba(70, 188, 255, 220);
            }

            QPushButton:checked {
                background: rgba(35, 166, 255, 215);
                border: 1px solid rgba(255, 255, 255, 190);
                color: #ffffff;
            }

            QLabel#ScopeSubtitle {
                color: #c8d4e0;
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
                border: 1px solid rgba(31, 92, 255, 80);
                border-radius: 12px;
                background: rgba(10, 14, 22, 240);
            }
            QFrame#SnapshotCard:hover {
                border: 1px solid rgba(31, 141, 218, 200);
                background: rgba(14, 20, 32, 255);
            }

            QPushButton {
                padding: 6px 14px;
                border-radius: 8px;
                border: 1px solid rgba(31, 92, 255, 100);
                background: rgba(15, 20, 35, 220);
                color: #c8d4e0;
                font: 700 8pt "DejaVu Sans Mono";
            }

            QPushButton:hover {
                background: rgba(31, 141, 218, 50);
                border: 1px solid rgba(31, 141, 218, 200);
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
            """
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(16)

        left = QHBoxLayout()
        left.setSpacing(14)

        icon_label = icon_badge(SNAPSHOT_GLYPH, 38)

        text_block = QVBoxLayout()
        text_block.setSpacing(3)

        title = QLabel(entry.path.name)
        title.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        title.setStyleSheet("color: #ecf4ff;")

        meta = QLabel(entry.meta_text)
        meta.setFont(QFont("DejaVu Sans Mono", 8))
        meta.setStyleSheet("color: #6b7a8d;")

        text_block.addWidget(title)
        text_block.addWidget(meta)

        left.addWidget(icon_label)
        left.addLayout(text_block)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_restore = QPushButton("RESTORE")
        self.btn_restore.setIcon(qta.icon(RESTORE_GLYPH, color="#FFFFFF"))
        self.btn_restore.setIconSize(QSize(16, 16))

        self.btn_integrity = QPushButton("INTEGRITY")
        self.btn_integrity.setIcon(qta.icon(INTEGRITY_GLYPH, color="#FFFFFF"))
        self.btn_integrity.setIconSize(QSize(16, 16))

        self.btn_delete = QPushButton("DELETE")
        self.btn_delete.setIcon(qta.icon(DELETE_GLYPH, color="#ff8888"))
        self.btn_delete.setIconSize(QSize(16, 16))
        self.btn_delete.setObjectName("DangerButton")

        btn_row.addWidget(self.btn_restore)
        btn_row.addWidget(self.btn_integrity)
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
                border: 1px solid rgba(31, 92, 255, 55);
                border-radius: 18px;
                background: rgba(8, 12, 20, 150);
            }
            """
        )
        control_layout = QHBoxLayout(self.control_card)
        control_layout.setContentsMargins(18, 16, 18, 16)
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
                border: 1px solid rgba(31, 141, 218, 255);
                border-radius: 16px;
                background: rgba(8, 12, 20, 120);
            }
            """
        )

        right_panel = QVBoxLayout(self.right_frame)
        right_panel.setContentsMargins(16, 12, 16, 12)
        right_panel.setSpacing(2)

        top_summary = QHBoxLayout()
        top_summary.setSpacing(8)
        top_summary.setAlignment(Qt.AlignVCenter)

        self.destination_badge = icon_badge(DEST_GLYPH, 36)

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
        space_row.setContentsMargins(50, -18, 0, 0)
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
        root.addWidget(self.control_card)
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
            empty.setStyleSheet(
                """
                QFrame {
                    border: 1px solid rgba(31, 92, 255, 55);
                    border-radius: 16px;
                    background: rgba(8, 12, 20, 120);
                }
                """
            )
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(22, 22, 22, 22)

            label = QLabel("No snapshots found for this destination.")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #9aa6b2;")
            label.setFont(QFont("DejaVu Sans Mono", 10))
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
                card.btn_integrity.clicked.connect(
                    lambda _, e=entry: self.check_integrity(e)
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
            QMessageBox.critical(self, "Carbonara Backup", str(e))

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

        # rc=0 → sucesso silencioso
        # rc=2 → cancelamento intencional pelo usuário (BackupProgressDialog.done(2))
        # rc=anything else → erro real
        if rc not in (0, 2):
            QMessageBox.warning(
                self,
                "Carbonara",
                f"Backup process exited with code {rc}.",
            )

    def restore_snapshot(self, entry: SnapshotEntry):
        if OperationManager.is_running():
            QMessageBox.warning(
                self,
                "Carbonara",
                "Another exclusive operation is already running.",
            )
            return

        QMessageBox.information(
            self,
            "Restore",
            f"Restore not implemented yet:\n\n{entry.path}",
        )

    def check_integrity(self, entry: SnapshotEntry):
        QMessageBox.information(
            self,
            "Integrity",
            f"Integrity check not implemented yet:\n\n{entry.path}",
        )

    def delete_snapshot(self, entry: SnapshotEntry):
        if OperationManager.is_running():
            QMessageBox.warning(
                self,
                "Carbonara",
                "Another exclusive operation is already running.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Snapshot",
            f"Delete snapshot?\n\n{entry.path}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        try:
            shutil.rmtree(entry.path)
            self.refresh_list()
        except Exception as e:
            QMessageBox.critical(self, "Delete Snapshot", str(e))
