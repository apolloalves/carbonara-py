from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

import os
import shutil
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QFrame,
)

from core.snapshots.backup import create_backup
from ui.widgets.backup_progress import BackupProgressDialog


SNAPSHOT_BASE = Path("/mnt/MDSATA/CarbonaraTS")


@dataclass(frozen=True)
class SnapshotEntry:
    kind: str
    path: Path
    size_text: str
    modified_text: str


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)

    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0

    return f"{size:.1f} PiB"


def dir_size(path: Path) -> int:
    total = 0

    if not path.exists():
        return 0

    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            try:
                total += item.stat().st_size
            except OSError:
                pass

    return total


def collect_snapshots() -> List[SnapshotEntry]:
    entries: List[SnapshotEntry] = []

    if not SNAPSHOT_BASE.exists():
        return entries

    for kind_dir in SNAPSHOT_BASE.iterdir():
        if not kind_dir.is_dir():
            continue

        for snap in sorted(
            [p for p in kind_dir.iterdir() if p.is_dir() and p.name != "latest"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                stat = snap.stat()

                entries.append(
                    SnapshotEntry(
                        kind=kind_dir.name,
                        path=snap,
                        size_text=human_size(dir_size(snap)),
                        modified_text=datetime.fromtimestamp(
                            stat.st_mtime
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                    )
                )
            except OSError:
                continue

    return entries


class SnapshotItem(QFrame):
    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)

        self.entry = entry

        self.setStyleSheet(
            """
            QFrame {
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 10px;
                background: rgba(8, 12, 20, 220);
            }

            QPushButton {
                padding: 6px 12px;
                border-radius: 8px;
                border: 1px solid rgba(31, 92, 255, 140);
                background: rgba(10, 15, 25, 230);
                color: #ecf4ff;
            }

            QPushButton:hover {
                background: rgba(23, 147, 209, 60);
            }
            """
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(4)

        title = QLabel(f"{entry.kind} • {entry.path.name}")
        title.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        title.setStyleSheet("color: #ecf4ff;")

        meta = QLabel(f"{entry.modified_text} • {entry.size_text}")
        meta.setFont(QFont("DejaVu Sans Mono", 9))
        meta.setStyleSheet("color: #9aa6b2;")

        left.addWidget(title)
        left.addWidget(meta)

        self.btn_restore = QPushButton("Restore")
        self.btn_integrity = QPushButton("Integrity")
        self.btn_delete = QPushButton("Delete")

        root.addLayout(left, 1)
        root.addWidget(self.btn_restore)
        root.addWidget(self.btn_integrity)
        root.addWidget(self.btn_delete)


class SnapshotsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.entries: list[SnapshotEntry] = []

        self.setStyleSheet(
            """
            QWidget {
                background: transparent;
            }

            QListWidget {
                border: none;
                background: transparent;
            }

            QListWidget::item {
                border: none;
                background: transparent;
                margin: 0px;
                padding: 0px;
            }

            QPushButton {
                padding: 8px 12px;
                border-radius: 8px;
                border: 1px solid rgba(31, 92, 255, 140);
                background: rgba(10, 15, 25, 230);
                color: #ecf4ff;
            }

            QPushButton:hover {
                background: rgba(23, 147, 209, 60);
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        top = QHBoxLayout()

        title = QLabel("Snapshots")
        title.setFont(QFont("DejaVu Sans Mono", 16, QFont.Bold))
        title.setStyleSheet("color: #23a6ff;")

        self.btn_refresh = QPushButton("Refresh")
        self.btn_create = QPushButton("Create Snapshot")

        self.btn_refresh.clicked.connect(self.refresh_list)
        self.btn_create.clicked.connect(self.create_snapshot)

        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_create)

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(8)

        root.addLayout(top)
        root.addWidget(self.list_widget, 1)

        self.refresh_list()

    def refresh_list(self):
        self.list_widget.clear()
        self.entries = collect_snapshots()

        if not self.entries:
            item = QListWidgetItem()

            label = QLabel("No snapshots found.")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(
                """
                color: #9aa6b2;
                padding: 24px;
                """
            )

            item.setSizeHint(label.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, label)
            return

        for entry in self.entries:
            item = QListWidgetItem()
            widget = SnapshotItem(entry)

            widget.btn_restore.clicked.connect(
                lambda _, e=entry: self.restore_snapshot(e)
            )
            widget.btn_integrity.clicked.connect(
                lambda _, e=entry: self.check_integrity(e)
            )
            widget.btn_delete.clicked.connect(
                lambda _, e=entry: self.delete_snapshot(e)
            )

            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

    def create_snapshot(self):
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
create_backup(dialog, scope='both')
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
            subprocess.Popen(cmd, cwd=str(project_root))
        except Exception as e:
            QMessageBox.critical(
                self,
                "Carbonara Backup",
                str(e),
            )

    def restore_snapshot(self, entry: SnapshotEntry):
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
            QMessageBox.critical(
                self,
                "Delete Snapshot",
                str(e),
            )
