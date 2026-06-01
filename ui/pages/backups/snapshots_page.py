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

from PySide6.QtCore import Qt, QTimer
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
)

from core.operation_manager import OperationManager
from core.system.storage import (
    StorageDestination,
    format_gb,
    list_backup_destinations,
)


# Glyphs no mesmo espírito do menu principal
DEST_GLYPH = "▣"
ROOT_GLYPH = "▣"
HOME_GLYPH = "⌂"
RESTORE_GLYPH = "↺"
INTEGRITY_GLYPH = "◉"
DELETE_GLYPH = "⌫"
REFRESH_GLYPH = "↻"
CREATE_GLYPH = "✚"
SNAPSHOT_GLYPH = "◌"


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


def glyph_badge(glyph: str, size: int = 34) -> QLabel:
    label = QLabel(glyph)
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(size, size)
    label.setFont(QFont("DejaVu Sans Mono", 16, QFont.Bold))
    label.setStyleSheet(
        """
        QLabel {
            color: #23a6ff;
            background: rgba(35, 166, 255, 28);
            border-radius: 10px;
        }
        """
    )
    return label


class SnapshotCard(QFrame):
    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.entry = entry

        self.setObjectName("SnapshotCard")
        self.setStyleSheet(
            """
            QFrame#SnapshotCard {
                border: 1px solid rgba(31, 92, 255, 70);
                border-radius: 14px;
                background: rgba(12, 16, 24, 225);
            }
            QFrame#SnapshotCard:hover {
                border: 1px solid rgba(35, 166, 255, 180);
                background: rgba(16, 22, 34, 245);
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

            QPushButton#DangerButton {
                border: 1px solid rgba(220, 80, 80, 120);
            }

            QPushButton#DangerButton:hover {
                background: rgba(220, 80, 80, 40);
                border: 1px solid rgba(255, 120, 120, 180);
            }
            """
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        left = QHBoxLayout()
        left.setSpacing(12)

        icon_label = glyph_badge(SNAPSHOT_GLYPH, 40)

        text_block = QVBoxLayout()
        text_block.setSpacing(4)

        title = QLabel(f"{entry.kind} • {entry.path.name}")
        title.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        title.setStyleSheet("color: #ecf4ff;")

        meta = QLabel(entry.meta_text)
        meta.setFont(QFont("DejaVu Sans Mono", 9))
        meta.setStyleSheet("color: #9aa6b2;")

        text_block.addWidget(title)
        text_block.addWidget(meta)

        left.addWidget(icon_label)
        left.addLayout(text_block)

        self.btn_restore = QPushButton(f"{RESTORE_GLYPH} Restore")
        self.btn_integrity = QPushButton(f"{INTEGRITY_GLYPH} Integrity")
        self.btn_delete = QPushButton(f"{DELETE_GLYPH} Delete")
        self.btn_delete.setObjectName("DangerButton")

        root.addLayout(left, 1)
        root.addWidget(self.btn_restore)
        root.addWidget(self.btn_integrity)
        root.addWidget(self.btn_delete)


class SectionCard(QFrame):
    def __init__(self, title_text: str, path_text: str, glyph: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SectionCard")
        self.setStyleSheet(
            """
            QFrame#SectionCard {
                border: 1px solid rgba(31, 92, 255, 55);
                border-radius: 16px;
                background: rgba(8, 12, 20, 145);
            }
            """
        )

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(16, 14, 16, 14)
        self.layout_main.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)

        icon_label = glyph_badge(glyph, 34)

        labels = QVBoxLayout()
        labels.setSpacing(2)

        title = QLabel(title_text)
        title.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        title.setStyleSheet("color: #ecf4ff;")

        path = QLabel(path_text)
        path.setFont(QFont("DejaVu Sans Mono", 9))
        path.setStyleSheet("color: #9aa6b2;")

        labels.addWidget(title)
        labels.addWidget(path)

        head.addWidget(icon_label)
        head.addLayout(labels)
        head.addStretch(1)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)

        self.layout_main.addLayout(head)
        self.layout_main.addLayout(self.body)


class SnapshotsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.entries: list[SnapshotEntry] = []
        self.destinations: list[StorageDestination] = []
        self._backup_proc: subprocess.Popen | None = None

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
                background: rgba(35, 166, 255, 210);
                border: 1px solid rgba(35, 166, 255, 255);
                color: #08111d;
                font-weight: bold;
            }

            QPushButton#PrimaryButton:hover {
                background: rgba(70, 188, 255, 235);
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

            QComboBox QAbstractItemView {
                background: #0a0f19;
                color: #ecf4ff;
                border: 1px solid rgba(31, 92, 255, 140);
                selection-background-color: #1f5cff;
                selection-color: #ecf4ff;
                outline: 0;
                padding: 4px;
            }

            QComboBox QAbstractItemView::item {
                min-height: 32px;
                padding: 8px 10px;
            }

            QComboBox QAbstractItemView::item:hover {
                background: rgba(23, 147, 209, 65);
            }

            QComboBox QAbstractItemView::item:selected {
                background: rgba(35, 166, 255, 180);
                color: #ecf4ff;
            }

            QScrollArea {
                border: none;
                background: transparent;
            }

            QScrollArea > QWidget > QWidget {
                background: transparent;
            }

            QLabel#Muted {
                color: #9aa6b2;
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
        control_layout.setSpacing(18)

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

        destination_block.addWidget(lbl_destination)
        destination_block.addWidget(self.cmb_destination)

        summary_block = QVBoxLayout()
        summary_block.setSpacing(6)

        top_summary = QHBoxLayout()
        top_summary.setSpacing(12)

        self.destination_badge = glyph_badge(DEST_GLYPH, 46)

        summary_text = QVBoxLayout()
        summary_text.setSpacing(4)

        self.lbl_destination_info = QLabel("Select a backup destination")
        self.lbl_destination_info.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        self.lbl_destination_info.setStyleSheet("color: #ecf4ff;")

        self.lbl_destination_meta = QLabel("—")
        self.lbl_destination_meta.setObjectName("Muted")
        self.lbl_destination_meta.setFont(QFont("DejaVu Sans Mono", 9))

        summary_text.addWidget(self.lbl_destination_info)
        summary_text.addWidget(self.lbl_destination_meta)

        top_summary.addWidget(self.destination_badge)
        top_summary.addLayout(summary_text)
        top_summary.addStretch(1)

        self.space_bar = QFrame()
        self.space_bar.setFixedHeight(8)
        self.space_bar.setStyleSheet(
            """
            QFrame {
                border: none;
                border-radius: 4px;
                background: rgba(255, 255, 255, 18);
            }
            """
        )

        self.space_fill = QFrame(self.space_bar)
        self.space_fill.setGeometry(0, 0, 0, 8)
        self.space_fill.setStyleSheet(
            """
            QFrame {
                border: none;
                border-radius: 4px;
                background: rgba(35, 166, 255, 210);
            }
            """
        )

        self.lbl_space_percent = QLabel("—")
        self.lbl_space_percent.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        self.lbl_space_percent.setStyleSheet("color: #4ade80;")

        summary_block.addLayout(top_summary)
        summary_block.addWidget(self.space_bar)
        summary_block.addWidget(self.lbl_space_percent)

        actions_block = QHBoxLayout()
        actions_block.setSpacing(10)

        self.btn_refresh = QPushButton(f"{REFRESH_GLYPH} Refresh")
        self.btn_create = QPushButton(f"{CREATE_GLYPH} Create Snapshot")
        self.btn_refresh.clicked.connect(self.refresh_destinations)
        self.btn_create.clicked.connect(self.create_snapshot)
        self.btn_create.setObjectName("PrimaryButton")

        actions_block.addWidget(self.btn_refresh)
        actions_block.addWidget(self.btn_create)

        actions_wrap = QVBoxLayout()
        actions_wrap.setSpacing(8)
        actions_wrap.addStretch(1)
        actions_wrap.addLayout(actions_block)

        control_layout.addLayout(destination_block, 3)
        control_layout.addLayout(summary_block, 3)
        control_layout.addLayout(actions_wrap, 2)

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

    def current_destination(self) -> StorageDestination | None:
        return self.cmb_destination.currentData()

    def _format_combo_item(self, dest: StorageDestination) -> str:
        return (
            f"{DEST_GLYPH} {dest.label}  •  {format_gb(dest.free_gb)} livre  •  "
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
            self.space_fill.setGeometry(0, 0, 0, 8)
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
            self.space_fill.setGeometry(0, 0, 0, 8)
            return

        used_pct = 0
        if dest.total_bytes > 0:
            used_pct = int(round((dest.used_bytes / dest.total_bytes) * 100))

        free_pct = max(0, 100 - used_pct)
        fill_width = max(0, int(self.space_bar.width() * used_pct / 100))
        self.space_fill.setGeometry(0, 0, fill_width, 8)

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
        self.update_destination_summary()
        self.rebuild_snapshot_view()

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
create_backup(dialog, destination_mountpoint={dest.mountpoint!r}, scope='both')
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
        self.refresh_list()

        if rc != 0:
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
