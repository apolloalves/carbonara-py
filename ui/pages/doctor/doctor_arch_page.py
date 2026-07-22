from __future__ import annotations

import math

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QFont, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFrame,
)

from core.system.doctor import run_full_checkup, DoctorReport, Finding

# Paleta alinhada ao main_window.py / disks_page.py (estilo SaaS)
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

LEVEL_COLOR = {"critical": ACCENT_RED, "warning": ACCENT_AMBER, "ok": ACCENT_GREEN}
LEVEL_LABEL = {"critical": "critico", "warning": "aviso", "ok": "ok"}


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


class HealthRing(QWidget):
    """Anel de saúde 0-100, cor semântica conforme a faixa."""

    def __init__(self, score: int = 100, size: int = 84, parent=None):
        super().__init__(parent)
        self._score = score
        self._size = size
        self.setFixedSize(size, size)

    def set_score(self, score: int) -> None:
        self._score = score
        self.update()

    def _color(self) -> QColor:
        if self._score >= 80:
            return QColor(ACCENT_GREEN)
        if self._score >= 50:
            return QColor(ACCENT_AMBER)
        return QColor(ACCENT_RED)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pad = 6
        rect = QRectF(pad, pad, self._size - 2 * pad, self._size - 2 * pad)

        bg_pen = QPen(QColor(255, 255, 255, 20))
        bg_pen.setWidth(8)
        bg_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        fg_pen = QPen(self._color())
        fg_pen.setWidth(8)
        fg_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(fg_pen)
        span = int(360 * 16 * (self._score / 100))
        painter.drawArc(rect, 90 * 16, -span)

        painter.setPen(QColor(TEXT))
        painter.setFont(QFont(FONT_FAMILY, int(self._size * 0.22), QFont.Bold))
        painter.drawText(self.rect(), Qt.AlignCenter, str(self._score))


class FindingRow(QFrame):
    """Linha compacta de um achado: bolinha de severidade + ícone + texto + ação."""

    def __init__(self, finding: Finding, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: #0d0e13; border: none; } QLabel { background: transparent; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(12)

        dot = QLabel("●")
        dot.setFont(QFont(FONT_FAMILY, 8))
        dot.setStyleSheet(f"color: {LEVEL_COLOR[finding.level]};")
        layout.addWidget(dot)

        icon = QLabel()
        icon.setPixmap(qta.icon("mdi6.alert-circle-outline", color=MUTED).pixmap(14, 14))
        layout.addWidget(icon)

        text_block = QVBoxLayout()
        text_block.setSpacing(1)
        title = QLabel(finding.title)
        title.setFont(QFont(FONT_FAMILY, 10))
        title.setStyleSheet(f"color: {TEXT};")
        detail = QLabel(finding.detail)
        detail.setFont(QFont(FONT_FAMILY, 8))
        detail.setStyleSheet(f"color: {FAINT};")
        text_block.addWidget(title)
        text_block.addWidget(detail)
        layout.addLayout(text_block, 1)

        if finding.fixable and finding.level != "ok":
            btn = QPushButton("Revisar")
            color = LEVEL_COLOR[finding.level]
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid rgba({_rgba(color, 100)});
                    color: {color};
                    border-radius: 7px;
                    padding: 5px 11px;
                    font-family: "{FONT_FAMILY}";
                    font-size: 9px;
                }}
                QPushButton:hover {{ background: rgba({_rgba(color, 20)}); }}
            """)
            layout.addWidget(btn)


class MiniCard(QFrame):
    """Card pequeno e discreto — usado pro Cleanup/Volumes/Watchlist no rodapé."""

    def __init__(self, icon_name: str, title: str, subtitle: str,
                 action_label: str | None = None, status: str | None = None,
                 status_color: str = ACCENT_GREEN, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                border: 1px solid rgba(255,255,255,12);
                border-radius: 14px;
                background: rgba(255,255,255,4);
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(qta.icon(icon_name, color=MUTED).pixmap(14, 14))
        top.addWidget(icon)
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont(FONT_FAMILY, 10, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT};")
        top.addWidget(title_lbl)
        top.addStretch()

        if action_label:
            btn = QPushButton(action_label)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,255,255,8);
                    border: none;
                    color: {TEXT};
                    border-radius: 7px;
                    padding: 5px 10px;
                    font-family: "{FONT_FAMILY}";
                    font-size: 9px;
                }}
                QPushButton:hover {{ background: rgba(255,255,255,14); }}
            """)
            top.addWidget(btn)
        elif status:
            status_lbl = QLabel(status)
            status_lbl.setFont(QFont(FONT_FAMILY, 9))
            status_lbl.setStyleSheet(f"color: {status_color};")
            top.addWidget(status_lbl)

        layout.addLayout(top)

        sub = QLabel(subtitle)
        sub.setFont(QFont(FONT_FAMILY, 8))
        sub.setStyleSheet(f"color: {FAINT};")
        layout.addWidget(sub)


class CheckupWorker(QThread):
    finished_checkup = Signal(object)

    def run(self) -> None:
        report = run_full_checkup()
        self.finished_checkup.emit(report)


class DoctorArchPage(QWidget):
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
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        self.btn_back = QPushButton("←  Back to menu")
        self.btn_back.setObjectName("BackButton")
        self.btn_back.setFixedWidth(140)
        self.btn_back.clicked.connect(self.back_requested.emit)
        root.addWidget(self.btn_back)

        header_row = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        page_title = QLabel("Doctor Arch")
        page_title.setFont(QFont(FONT_FAMILY, 20, QFont.Bold))
        page_title.setStyleSheet(f"color: {TEXT};")
        page_sub = QLabel("Diagnose, clean and repair your Arch install")
        page_sub.setFont(QFont(FONT_FAMILY, 9))
        page_sub.setStyleSheet(f"color: {MUTED};")
        title_block.addWidget(page_title)
        title_block.addWidget(page_sub)

        self.btn_checkup = QPushButton("↻  Rodar checkup")
        self.btn_checkup.clicked.connect(self.run_checkup)

        header_row.addLayout(title_block)
        header_row.addStretch()
        header_row.addWidget(self.btn_checkup)
        root.addLayout(header_row)

        # ── Hero: health score ──────────────────────────────────────────
        self.hero = QFrame()
        self.hero.setStyleSheet("""
            QFrame { border: 1px solid rgba(255,255,255,12); border-radius: 14px; background: rgba(255,255,255,4); }
            QLabel { background: transparent; border: none; }
        """)
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(20, 18, 20, 18)
        hero_layout.setSpacing(20)

        self.ring = HealthRing(100)
        hero_layout.addWidget(self.ring)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(6)
        self.hero_title = QLabel("Rodando checkup...")
        self.hero_title.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
        self.hero_title.setStyleSheet(f"color: {TEXT};")
        self.hero_status = QLabel("")
        self.hero_status.setFont(QFont(FONT_FAMILY, 9))
        self.hero_status.setStyleSheet(f"color: {FAINT};")
        hero_text.addWidget(self.hero_title)
        hero_text.addWidget(self.hero_status)
        hero_layout.addLayout(hero_text, 1)

        root.addWidget(self.hero)

        # ── Findings list ────────────────────────────────────────────────
        lbl_findings = QLabel("ENCONTRADOS")
        lbl_findings.setFont(QFont(FONT_FAMILY, 9, QFont.Bold))
        lbl_findings.setStyleSheet(f"color: {FAINT}; letter-spacing: 0.5px;")
        root.addWidget(lbl_findings)

        self.findings_container = QVBoxLayout()
        self.findings_container.setSpacing(1)
        findings_frame = QFrame()
        findings_frame.setStyleSheet("""
            QFrame { border: 1px solid rgba(255,255,255,12); border-radius: 14px; }
        """)
        findings_frame.setLayout(self.findings_container)
        root.addWidget(findings_frame)

        # ── Rodapé: mini cards ───────────────────────────────────────────
        self.mini_row = QGridLayout()
        self.mini_row.setSpacing(14)
        root.addLayout(self.mini_row)

        root.addStretch()

        self._worker: CheckupWorker | None = None
        self.run_checkup()

    def run_checkup(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.btn_checkup.setEnabled(False)
        self.hero_title.setText("Rodando checkup...")
        worker = CheckupWorker(parent=self)
        worker.finished_checkup.connect(self._on_checkup_done)
        self._worker = worker
        worker.start()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_checkup_done(self, report: DoctorReport) -> None:
        self.btn_checkup.setEnabled(True)
        self.ring.set_score(report.score)

        if report.critical_count == 0 and report.warning_count == 0:
            self.hero_title.setText("Sistema saudável")
        else:
            parts = []
            if report.critical_count:
                parts.append(f"{report.critical_count} crítico(s)")
            if report.warning_count:
                parts.append(f"{report.warning_count} aviso(s)")
            self.hero_title.setText(" e ".join(parts) + " encontrados")

        self.hero_status.setText("Última verificação: agora")

        self._clear_layout(self.findings_container)
        actionable = [f for f in report.findings if f.level != "ok"]
        if not actionable:
            ok_row = QLabel("Nenhum achado — tudo em ordem.")
            ok_row.setFont(QFont(FONT_FAMILY, 10))
            ok_row.setStyleSheet(f"color: {MUTED}; padding: 16px;")
            self.findings_container.addWidget(ok_row)
        else:
            for finding in actionable:
                self.findings_container.addWidget(FindingRow(finding))

        self._clear_layout(self.mini_row)
        cleanup_card = MiniCard("mdi6.broom", "Limpeza", "~2.4 GB em 5 categorias", action_label="Limpar")
        volumes_finding = next((f for f in report.findings if f.id == "volumes"), None)
        volumes_card = MiniCard(
            "mdi6.harddisk", "Volumes",
            volumes_finding.detail if volumes_finding else "não verificado",
            status="ok" if volumes_finding and volumes_finding.level == "ok" else "atenção",
            status_color=ACCENT_GREEN if volumes_finding and volumes_finding.level == "ok" else ACCENT_RED,
        )
        aur_finding = next((f for f in report.findings if f.id.startswith("aur_")), None)
        aur_card = MiniCard(
            "mdi6.eye-outline", "Watchlist AUR",
            aur_finding.detail if aur_finding else "nenhum pacote observado",
            status="1 pacote" if aur_finding else None,
            status_color=ACCENT_BLUE_LIGHT,
        )
        self.mini_row.addWidget(cleanup_card, 0, 0)
        self.mini_row.addWidget(volumes_card, 0, 1)
        self.mini_row.addWidget(aur_card, 0, 2)
