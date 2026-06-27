from __future__ import annotations

from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QPlainTextEdit,
)

from core.system.disks import (
    list_disks,
    get_raid_info,
    get_disk_temps,
    get_large_volumes,
    find_large_files,
    DiskInfo,
    RaidInfo,
)

DISK_GLYPH = "mdi6.harddisk"
RAID_GLYPH = "mdi6.view-grid-outline"
TEMP_GLYPH = "mdi6.thermometer"
SCAN_GLYPH = "mdi6.magnify"
REFRESH_GLYPH = "mdi6.refresh"
WARN_GLYPH = "mdi6.alert-circle-outline"

# Paleta alinhada ao main_window.py (estilo SaaS)
BG = "#0a0b0f"
TEXT = "#e4e7ec"
MUTED = "#8b92a3"
FAINT = "#6b7280"

ACCENT_BLUE = "#3b82f6"
ACCENT_BLUE_LIGHT = "#60a5fa"
ACCENT_PURPLE = "#8b5cf6"
ACCENT_GREEN = "#34d399"
ACCENT_AMBER = "#fbbf24"
ACCENT_RED = "#f87171"

FONT_FAMILY = "DejaVu Sans Mono"


def _rgba(hex_color: str, alpha: int) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r}, {g}, {b}, {alpha}"


def icon_badge(icon_name: str, size: int = 34, color: str = TEXT, bg: str = "rgba(255,255,255,8)") -> QLabel:
    label = QLabel()
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(size, size)
    label.setPixmap(qta.icon(icon_name, color=color).pixmap(int(size * 0.5)))
    label.setStyleSheet(f"QLabel {{ background: {bg}; border-radius: {int(size * 0.28)}px; }}")
    return label


class DiskRow(QFrame):
    """Linha de disco no estilo card SaaS, com barra de uso e cor semântica."""

    def __init__(self, disk: DiskInfo, parent=None):
        super().__init__(parent)
        self.setObjectName("DiskRow")
        self.setFixedHeight(108)
        self.setFocusPolicy(Qt.NoFocus)

        has_data = bool(disk.use_pct)
        try:
            pct = int(disk.use_pct.rstrip("%")) if disk.use_pct else 0
        except ValueError:
            pct = 0
            has_data = False

        if not has_data:
            bar_color = FAINT
            border_tint = "255, 255, 255, 14"
            bg_tint = "rgba(255, 255, 255, 5)"
        elif pct >= 90:
            bar_color = ACCENT_RED
            border_tint = _rgba(ACCENT_RED, 45)
            bg_tint = f"rgba({_rgba(ACCENT_RED, 10)})"
        elif pct >= 75:
            bar_color = ACCENT_AMBER
            border_tint = _rgba(ACCENT_AMBER, 45)
            bg_tint = f"rgba({_rgba(ACCENT_AMBER, 10)})"
        else:
            bar_color = ACCENT_GREEN
            border_tint = "255, 255, 255, 20"
            bg_tint = "rgba(255, 255, 255, 10)"

        self.setStyleSheet(f"""
            QFrame#DiskRow {{
                border: 1px solid rgba({border_tint});
                border-radius: 14px;
                background: {bg_tint};
            }}
            QFrame#DiskRow:hover {{
                border: 1px solid rgba({_rgba(ACCENT_BLUE_LIGHT, 90)});
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        icon_bg = f"rgba({_rgba(bar_color, 28)})" if has_data and pct >= 75 else "rgba(255,255,255,8)"
        icon = icon_badge(DISK_GLYPH, 32, color=TEXT, bg=icon_bg)

        text_block = QVBoxLayout()
        text_block.setSpacing(1)
        text_block.setContentsMargins(0, 0, 0, 0)

        title = QLabel(disk.mountpoint)
        title.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT};")

        meta = QLabel(f"{disk.path} · {disk.fstype}")
        meta.setFont(QFont(FONT_FAMILY, 9))
        meta.setStyleSheet(f"color: {FAINT};")

        text_block.addWidget(title)
        text_block.addWidget(meta)

        top_row.addWidget(icon)
        top_row.addLayout(text_block, 1)

        if has_data:
            avail_lbl = QLabel(f"{disk.avail} free")
            avail_lbl.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
            avail_lbl.setStyleSheet(f"color: {bar_color};")
            avail_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            top_row.addWidget(avail_lbl, 0, Qt.AlignVCenter)

        root.addLayout(top_row)
        root.addStretch()

        if has_data:
            bar_bg = QFrame()
            bar_bg.setFixedHeight(5)
            bar_bg.setStyleSheet("QFrame { border-radius: 3px; background: rgba(255,255,255,10); border: none; }")
            self._bar_bg = bar_bg
            bar_fill = QFrame(bar_bg)
            bar_fill.setStyleSheet(f"""
                QFrame {{
                    border-radius: 3px;
                    border: none;
                    background: {bar_color};
                }}
            """)
            self._bar_fill = bar_fill
            self._pct = pct

            usage_lbl = QLabel(f"{disk.used} / {disk.size} · {disk.use_pct}")
            usage_lbl.setFont(QFont(FONT_FAMILY, 9))
            usage_lbl.setStyleSheet(f"color: {MUTED};")

            root.addWidget(bar_bg)
            root.addSpacing(5)
            root.addWidget(usage_lbl)
        else:
            no_data_lbl = QLabel("no usage data")
            no_data_lbl.setFont(QFont(FONT_FAMILY, 9))
            no_data_lbl.setStyleSheet(f"color: {FAINT};")
            root.addWidget(no_data_lbl)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_bar_bg") and hasattr(self, "_bar_fill"):
            w = max(2, int(self._bar_bg.width() * self._pct / 100))
            self._bar_fill.setGeometry(0, 0, w, self._bar_bg.height())


class RaidCard(QFrame):
    """Card de status do array RAID — alinhado ao HeroCard do menu principal."""

    def __init__(self, raid: RaidInfo | None, parent=None):
        super().__init__(parent)
        self.setObjectName("RaidCard")

        is_healthy = raid is not None and raid.state == "clean"

        if raid is None:
            bg = "rgba(255,255,255,6)"
            border = "1px solid rgba(255,255,255,12)"
        elif is_healthy:
            bg = f"rgba({_rgba(ACCENT_GREEN, 15)})"
            border = f"1px solid rgba({_rgba(ACCENT_GREEN, 60)})"
        else:
            bg = f"rgba({_rgba(ACCENT_RED, 15)})"
            border = f"1px solid rgba({_rgba(ACCENT_RED, 60)})"

        self.setStyleSheet(f"""
            QFrame#RaidCard {{
                border: {border};
                border-radius: 16px;
                background: {bg};
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)

        badge_color = ACCENT_GREEN if is_healthy else (ACCENT_RED if raid else MUTED)
        icon_bg = f"rgba({_rgba(badge_color, 22)})"
        icon = icon_badge(RAID_GLYPH, 40, color=badge_color, bg=icon_bg)

        text_block = QVBoxLayout()
        text_block.setSpacing(3)

        if raid:
            title_row = QHBoxLayout()
            title_row.setSpacing(10)

            title = QLabel(raid.device)
            title.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
            title.setStyleSheet(f"color: {TEXT};")

            level_label = raid.level.replace("raid", "RAID ")
            status_text = "CLEAN" if is_healthy else "DEGRADED"
            badge = QLabel(f"{level_label.upper()} · {status_text}")
            badge.setFont(QFont(FONT_FAMILY, 8, QFont.Bold))
            badge.setStyleSheet(f"""
                color: {badge_color};
                background: rgba({_rgba(badge_color, 28)});
                border-radius: 7px;
                padding: 3px 9px;
            """)

            title_row.addWidget(title)
            title_row.addWidget(badge, 0, Qt.AlignVCenter)
            title_row.addStretch()

            meta = QLabel(f"{raid.array_size} · {len(raid.members)} members · {' + '.join(raid.members)}")
            meta.setFont(QFont(FONT_FAMILY, 9))
            meta.setStyleSheet(f"color: {MUTED};")

            text_block.addLayout(title_row)
            text_block.addWidget(meta)
        else:
            title = QLabel("No RAID array detected")
            title.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
            title.setStyleSheet(f"color: {MUTED};")
            text_block.addWidget(title)

        layout.addWidget(icon)
        layout.addLayout(text_block, 1)


class TempBadge(QFrame):
    """Badge de temperatura de um disco."""

    def __init__(self, device: str, temp: str, parent=None):
        super().__init__(parent)
        try:
            value = int(temp.rstrip("°C"))
        except ValueError:
            value = 0

        if value >= 55:
            color = ACCENT_RED
        elif value >= 45:
            color = ACCENT_AMBER
        else:
            color = ACCENT_GREEN

        self.setStyleSheet(f"""
            QFrame {{
                border: 1px solid rgba({_rgba(color, 60)});
                border-radius: 10px;
                background: rgba({_rgba(color, 14)});
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(8)

        icon = QLabel()
        icon.setPixmap(qta.icon(TEMP_GLYPH, color=color).pixmap(14, 14))

        dev_lbl = QLabel(device)
        dev_lbl.setFont(QFont(FONT_FAMILY, 9, QFont.Bold))
        dev_lbl.setStyleSheet(f"color: {color};")

        temp_lbl = QLabel(temp)
        temp_lbl.setFont(QFont(FONT_FAMILY, 9, QFont.Bold))
        temp_lbl.setStyleSheet(f"color: {color};")

        layout.addWidget(icon)
        layout.addWidget(dev_lbl)
        layout.addWidget(temp_lbl)


class ScanWorker(QThread):
    """Roda find de arquivos grandes em background."""
    finished_scan = Signal(list)

    def __init__(self, path: str = "/", min_size_mb: int = 500, parent=None):
        super().__init__(parent)
        self._path = path
        self._min_size_mb = min_size_mb

    def run(self) -> None:
        results = find_large_files(self._path, self._min_size_mb)
        self.finished_scan.emit(results)


class DisksPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet(f"""
            QWidget {{ background: transparent; }}
            QPushButton {{
                padding: 9px 16px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 14);
                background: rgba(255, 255, 255, 6);
                color: {TEXT};
                font-family: "{FONT_FAMILY}";
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 24);
            }}
            QPushButton#PrimaryButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {ACCENT_BLUE}, stop:1 {ACCENT_PURPLE}
                );
                border: none;
                color: white;
            }}
            QPushButton#PrimaryButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {ACCENT_BLUE_LIGHT}, stop:1 {ACCENT_PURPLE}
                );
            }}
            QPushButton#BackButton {{
                background: transparent;
                border: none;
                color: {MUTED};
                font-weight: normal;
                padding: 4px 0px;
            }}
            QPushButton#BackButton:hover {{
                color: {TEXT};
                background: transparent;
            }}
            QScrollArea {{ border: none; background: transparent; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QPlainTextEdit {{
                background: rgba(255, 255, 255, 4);
                border: 1px solid rgba(255, 255, 255, 10);
                border-radius: 10px;
                color: {TEXT};
                font-family: "{FONT_FAMILY}";
                font-size: 10px;
                padding: 10px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # ── Botão voltar ─────────────────────────────────────────────────
        self.btn_back = QPushButton("←  Back to menu")
        self.btn_back.setObjectName("BackButton")
        self.btn_back.setFixedWidth(140)
        self.btn_back.clicked.connect(self.back_requested.emit)
        root.addWidget(self.btn_back)

        # ── Cabeçalho com botões ──────────────────────────────────────────
        header_row = QHBoxLayout()

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        page_title = QLabel("Disks")
        page_title.setFont(QFont(FONT_FAMILY, 20, QFont.Bold))
        page_title.setStyleSheet(f"color: {TEXT};")
        page_sub = QLabel("Space, RAID, temperature & large files")
        page_sub.setFont(QFont(FONT_FAMILY, 9))
        page_sub.setStyleSheet(f"color: {MUTED};")
        title_block.addWidget(page_title)
        title_block.addWidget(page_sub)

        self.btn_refresh = QPushButton("↻  Refresh")
        self.btn_refresh.clicked.connect(self.refresh_all)

        self.btn_scan = QPushButton("⌕  Scan large files")
        self.btn_scan.setObjectName("PrimaryButton")
        self.btn_scan.clicked.connect(self.run_scan)

        header_row.addLayout(title_block)
        header_row.addStretch()
        header_row.addWidget(self.btn_refresh)
        header_row.addWidget(self.btn_scan)

        root.addLayout(header_row)

        # ── RAID card ────────────────────────────────────────────────────
        self.raid_container = QVBoxLayout()
        root.addLayout(self.raid_container)

        # ── Lista de discos ──────────────────────────────────────────────
        lbl_disks = QLabel("MOUNTED VOLUMES")
        lbl_disks.setFont(QFont(FONT_FAMILY, 9, QFont.Bold))
        lbl_disks.setStyleSheet(f"color: {FAINT}; letter-spacing: 0.5px;")
        root.addWidget(lbl_disks)

        self.disks_container = QGridLayout()
        self.disks_container.setSpacing(10)
        root.addLayout(self.disks_container)

        # ── Temperaturas (rodapé discreto) ──────────────────────────────
        self.temp_row = QHBoxLayout()
        self.temp_row.setSpacing(8)
        root.addLayout(self.temp_row)

        # ── Resultado do scan (oculto por padrão) ───────────────────────
        self.scan_frame = QFrame()
        self.scan_frame.setVisible(False)
        scan_layout = QVBoxLayout(self.scan_frame)
        scan_layout.setContentsMargins(0, 8, 0, 0)
        scan_layout.setSpacing(8)

        scan_header = QHBoxLayout()
        lbl_scan = QLabel("LARGE FILES (>500 MB)")
        lbl_scan.setFont(QFont(FONT_FAMILY, 9, QFont.Bold))
        lbl_scan.setStyleSheet(f"color: {FAINT}; letter-spacing: 0.5px;")
        self.lbl_scan_status = QLabel("")
        self.lbl_scan_status.setFont(QFont(FONT_FAMILY, 9))
        self.lbl_scan_status.setStyleSheet(f"color: {MUTED};")
        scan_header.addWidget(lbl_scan)
        scan_header.addStretch()
        scan_header.addWidget(self.lbl_scan_status)
        scan_layout.addLayout(scan_header)

        self.scan_output = QPlainTextEdit()
        self.scan_output.setReadOnly(True)
        self.scan_output.setFixedHeight(220)
        scan_layout.addWidget(self.scan_output)

        root.addWidget(self.scan_frame)

        self.scroll_spacer = QVBoxLayout()
        root.addLayout(self.scroll_spacer, 1)

        self._scan_worker: ScanWorker | None = None

        self.refresh_all()

    # ------------------------------------------------------------------ data --

    def refresh_all(self) -> None:
        self._refresh_raid()
        self._refresh_disks()
        self._refresh_temps()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_raid(self) -> None:
        self._clear_layout(self.raid_container)
        raid = get_raid_info()
        self.raid_container.addWidget(RaidCard(raid))

    def _refresh_temps(self) -> None:
        self._clear_layout(self.temp_row)
        temps = get_disk_temps()
        if not temps:
            lbl = QLabel("⚠  Temperatures unavailable — requires sudo/hddtemp")
            lbl.setFont(QFont(FONT_FAMILY, 9))
            lbl.setStyleSheet(f"color: {FAINT};")
            self.temp_row.addWidget(lbl)
        else:
            for device, temp in temps.items():
                self.temp_row.addWidget(TempBadge(device, temp))
        self.temp_row.addStretch()

    def _refresh_disks(self) -> None:
        self._clear_layout(self.disks_container)
        disks = list_disks()
        if not disks:
            lbl = QLabel("No mounted disks found.")
            lbl.setFont(QFont(FONT_FAMILY, 9))
            lbl.setStyleSheet(f"color: {MUTED};")
            self.disks_container.addWidget(lbl, 0, 0)
            return
        for i, disk in enumerate(disks):
            row, col = divmod(i, 2)
            self.disks_container.addWidget(DiskRow(disk), row, col)

    def run_scan(self) -> None:
        if self._scan_worker is not None and self._scan_worker.isRunning():
            return

        self.scan_frame.setVisible(True)
        self.scan_output.clear()
        self.lbl_scan_status.setText("Searching...")
        self.btn_scan.setEnabled(False)

        worker = ScanWorker(path="/", min_size_mb=500, parent=self)
        worker.finished_scan.connect(self._on_scan_done)
        self._scan_worker = worker
        worker.start()

    def _on_scan_done(self, results: list) -> None:
        self.btn_scan.setEnabled(True)
        if not results:
            self.lbl_scan_status.setText("No large files found.")
            return

        self.lbl_scan_status.setText(f"{len(results)} file(s) found")
        for size, path in results:
            self.scan_output.appendPlainText(f"{size:>10}   {path}")
