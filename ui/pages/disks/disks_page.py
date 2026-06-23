from __future__ import annotations

from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
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
RAID_GLYPH = "mdi6.layers-triple-outline"
TEMP_GLYPH = "mdi6.thermometer"
SCAN_GLYPH = "mdi6.file-find-outline"
REFRESH_GLYPH = "mdi6.refresh"
WARN_GLYPH = "mdi6.alert-circle-outline"


def icon_badge(icon_name: str, size: int = 34, color: str = "#FFFFFF", bg: str = "rgba(35, 166, 255, 34)") -> QLabel:
    label = QLabel()
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(size, size)
    label.setPixmap(qta.icon(icon_name, color=color).pixmap(size - 2, size - 2))
    label.setStyleSheet(f"QLabel {{ background: {bg}; border-radius: 10px; }}")
    return label


class DiskRow(QFrame):
    """Linha de disco no estilo card do Carbonara, com barra de uso."""

    def __init__(self, disk: DiskInfo, parent=None):
        super().__init__(parent)
        self.setObjectName("DiskRow")

        try:
            pct = int(disk.use_pct.rstrip("%")) if disk.use_pct else 0
        except ValueError:
            pct = 0

        if pct >= 90:
            bar_color = "#ff6666"
        elif pct >= 75:
            bar_color = "#ffaa66"
        else:
            bar_color = "#4ade80"

        self.setStyleSheet(f"""
            QFrame#DiskRow {{
                border: 1px solid rgba(31, 92, 255, 80);
                border-radius: 12px;
                background: rgba(10, 14, 22, 240);
            }}
            QFrame#DiskRow:hover {{
                border: 1px solid rgba(31, 141, 218, 200);
                background: rgba(14, 20, 32, 255);
            }}
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(14)

        icon = icon_badge(DISK_GLYPH, 32)

        text_block = QVBoxLayout()
        text_block.setSpacing(2)

        title = QLabel(f"{disk.mountpoint}")
        title.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        title.setStyleSheet("color: #ecf4ff;")

        meta = QLabel(f"{disk.path}  •  {disk.fstype}  •  {disk.model or 'sem modelo'}")
        meta.setFont(QFont("DejaVu Sans Mono", 8))
        meta.setStyleSheet("color: #6b7a8d;")

        text_block.addWidget(title)
        text_block.addWidget(meta)

        bar_block = QVBoxLayout()
        bar_block.setSpacing(3)

        bar_bg = QFrame()
        bar_bg.setFixedSize(180, 6)
        bar_bg.setStyleSheet("QFrame { border-radius: 3px; background: rgba(255,255,255,18); }")
        bar_fill = QFrame(bar_bg)
        fill_width = max(2, int(180 * pct / 100))
        bar_fill.setGeometry(0, 0, fill_width, 6)
        bar_fill.setStyleSheet(f"QFrame {{ border-radius: 3px; background: {bar_color}; }}")

        usage_lbl = QLabel(f"{disk.used} / {disk.size}  ({disk.use_pct})")
        usage_lbl.setFont(QFont("DejaVu Sans Mono", 8, QFont.Bold))
        usage_lbl.setStyleSheet(f"color: {bar_color};")
        usage_lbl.setAlignment(Qt.AlignRight)

        bar_block.addWidget(bar_bg)
        bar_block.addWidget(usage_lbl)

        avail_lbl = QLabel(f"{disk.avail} livre")
        avail_lbl.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        avail_lbl.setStyleSheet("color: #4ade80;")
        avail_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        avail_lbl.setFixedWidth(90)

        root.addWidget(icon)
        root.addLayout(text_block, 1)
        root.addLayout(bar_block)
        root.addWidget(avail_lbl)


class RaidCard(QFrame):
    """Card de status do array RAID."""

    def __init__(self, raid: RaidInfo | None, parent=None):
        super().__init__(parent)
        self.setObjectName("RaidCard")
        self.setStyleSheet("""
            QFrame#RaidCard {
                border: 1px solid rgba(31, 141, 218, 255);
                border-radius: 16px;
                background: rgba(8, 12, 20, 120);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        icon = icon_badge(RAID_GLYPH, 36)

        text_block = QVBoxLayout()
        text_block.setSpacing(2)

        if raid:
            title = QLabel(f"{raid.device}  •  RAID {raid.level.replace('raid', '')}")
            title.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
            title.setStyleSheet("color: #ecf4ff;")

            state_color = "#4ade80" if raid.state == "clean" else "#ff9966"
            meta = QLabel(f"{raid.array_size}  •  {len(raid.members)} membros  •  {raid.state}")
            meta.setFont(QFont("DejaVu Sans Mono", 9))
            meta.setStyleSheet(f"color: {state_color};")

            members = QLabel("  ".join(raid.members))
            members.setFont(QFont("DejaVu Sans Mono", 8))
            members.setStyleSheet("color: #6b7a8d;")

            text_block.addWidget(title)
            text_block.addWidget(meta)
            text_block.addWidget(members)
        else:
            title = QLabel("Nenhum array RAID detectado")
            title.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
            title.setStyleSheet("color: #9aa6b2;")
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
            color = "#ff6666"
        elif value >= 45:
            color = "#ffaa66"
        else:
            color = "#4ade80"

        self.setStyleSheet(f"""
            QFrame {{
                border: 1px solid rgba({self._rgba(color)});
                border-radius: 10px;
                background: rgba({self._rgba(color, 20)});
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        icon = QLabel()
        icon.setPixmap(qta.icon(TEMP_GLYPH, color=color).pixmap(16, 16))
        icon.setStyleSheet("background: transparent;")

        dev_lbl = QLabel(device)
        dev_lbl.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        dev_lbl.setStyleSheet(f"color: {color}; background: transparent;")

        temp_lbl = QLabel(temp)
        temp_lbl.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        temp_lbl.setStyleSheet(f"color: {color}; background: transparent;")

        layout.addWidget(icon)
        layout.addWidget(dev_lbl)
        layout.addWidget(temp_lbl)

    @staticmethod
    def _rgba(hex_color: str, alpha: int = 120) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r}, {g}, {b}, {alpha}"


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

        self.setStyleSheet("""
            QWidget { background: transparent; }
            QPushButton {
                padding: 8px 14px;
                border-radius: 10px;
                border: 1px solid rgba(31, 92, 255, 120);
                background: rgba(10, 15, 25, 230);
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
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
            }
            QScrollArea { border: none; background: transparent; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QPlainTextEdit {
                background: rgba(6, 9, 16, 200);
                border: 1px solid rgba(31, 92, 255, 55);
                border-radius: 8px;
                color: #c8d4e0;
                font-family: "DejaVu Sans Mono";
                font-size: 10px;
                padding: 8px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # ── Botão voltar ─────────────────────────────────────────────────
        self.btn_back = QPushButton("←  Back to menu")
        self.btn_back.setFixedWidth(160)
        self.btn_back.clicked.connect(self.back_requested.emit)
        root.addWidget(self.btn_back)

        # ── Cabeçalho com botões ──────────────────────────────────────────
        header_row = QHBoxLayout()

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        page_title = QLabel("Disks")
        page_title.setFont(QFont("DejaVu Sans Mono", 18, QFont.Bold))
        page_title.setStyleSheet("color: #23a6ff;")
        page_sub = QLabel("Espaço, RAID, temperatura e arquivos grandes")
        page_sub.setFont(QFont("DejaVu Sans Mono", 9))
        page_sub.setStyleSheet("color: #6b7a8d;")
        title_block.addWidget(page_title)
        title_block.addWidget(page_sub)

        self.btn_refresh = QPushButton("REFRESH")
        self.btn_refresh.setIcon(qta.icon(REFRESH_GLYPH, color="#FFFFFF"))
        self.btn_refresh.setIconSize(QSize(16, 16))
        self.btn_refresh.clicked.connect(self.refresh_all)

        self.btn_scan = QPushButton("SCAN LARGE FILES")
        self.btn_scan.setIcon(qta.icon(SCAN_GLYPH, color="#08111d"))
        self.btn_scan.setIconSize(QSize(16, 16))
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

        # ── Temperaturas ─────────────────────────────────────────────────
        self.temp_row = QHBoxLayout()
        self.temp_row.setSpacing(10)
        root.addLayout(self.temp_row)

        # ── Lista de discos ──────────────────────────────────────────────
        lbl_disks = QLabel("Volumes montados")
        lbl_disks.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl_disks.setStyleSheet("color: #ecf4ff;")
        root.addWidget(lbl_disks)

        self.disks_container = QVBoxLayout()
        self.disks_container.setSpacing(8)
        root.addLayout(self.disks_container)

        # ── Resultado do scan (oculto por padrão) ───────────────────────
        self.scan_frame = QFrame()
        self.scan_frame.setVisible(False)
        scan_layout = QVBoxLayout(self.scan_frame)
        scan_layout.setContentsMargins(0, 8, 0, 0)
        scan_layout.setSpacing(6)

        scan_header = QHBoxLayout()
        lbl_scan = QLabel("Arquivos grandes (>500 MB)")
        lbl_scan.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl_scan.setStyleSheet("color: #ecf4ff;")
        self.lbl_scan_status = QLabel("")
        self.lbl_scan_status.setFont(QFont("DejaVu Sans Mono", 9))
        self.lbl_scan_status.setStyleSheet("color: #6b7a8d;")
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
        self._refresh_temps()
        self._refresh_disks()

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
            lbl = QLabel("Temperaturas indisponíveis (requer sudo/hddtemp)")
            lbl.setFont(QFont("DejaVu Sans Mono", 8))
            lbl.setStyleSheet("color: #6b7a8d;")
            self.temp_row.addWidget(lbl)
        else:
            for device, temp in temps.items():
                self.temp_row.addWidget(TempBadge(device, temp))
        self.temp_row.addStretch()

    def _refresh_disks(self) -> None:
        self._clear_layout(self.disks_container)
        disks = list_disks()
        if not disks:
            lbl = QLabel("Nenhum disco montado encontrado.")
            lbl.setFont(QFont("DejaVu Sans Mono", 9))
            lbl.setStyleSheet("color: #9aa6b2;")
            self.disks_container.addWidget(lbl)
            return
        for disk in disks:
            self.disks_container.addWidget(DiskRow(disk))

    def run_scan(self) -> None:
        if self._scan_worker is not None and self._scan_worker.isRunning():
            return

        self.scan_frame.setVisible(True)
        self.scan_output.clear()
        self.lbl_scan_status.setText("Buscando...")
        self.btn_scan.setEnabled(False)

        worker = ScanWorker(path="/", min_size_mb=500, parent=self)
        worker.finished_scan.connect(self._on_scan_done)
        self._scan_worker = worker
        worker.start()

    def _on_scan_done(self, results: list) -> None:
        self.btn_scan.setEnabled(True)
        if not results:
            self.lbl_scan_status.setText("Nenhum arquivo grande encontrado.")
            return

        self.lbl_scan_status.setText(f"{len(results)} arquivo(s) encontrado(s)")
        for size, path in results:
            self.scan_output.appendPlainText(f"{size:>10}   {path}")
