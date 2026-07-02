from __future__ import annotations

import sys
from dataclasses import dataclass

import qtawesome as qta
from PySide6.QtCore import Qt, QRect, QEvent, QPoint, QSize, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QBrush,
    QKeyEvent,
    QFontMetrics,
)

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.pages.backups.backups_page import BackupsPage
from ui.pages.eggs.eggs_page import EggsPage
from ui.pages.disks.disks_page import DisksPage
from core.system.sysinfo import get_system_info


# Paleta
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

APP_VERSION = "v2.4.0"
APP_AUTHOR = "Douglas Apollo Alves"

FONT_FAMILY = "DejaVu Sans Mono"


@dataclass(frozen=True)
class MenuEntry:
    number: int
    title: str
    desc: str
    short_desc: str
    glyph: str


MENU_ENTRIES = [
    MenuEntry(1, "Dashboard", "Monitor system information and quick status", "System status", "mdi6.view-dashboard"),
    MenuEntry(2, "Network", "Diagnose and configure network settings", "Wifi & links", "mdi6.wifi"),
    MenuEntry(3, "Packages", "Manage packages, mirrors and updates", "Mirrors & updates", "mdi6.package-variant"),
    MenuEntry(4, "Backups", "Create, restore and verify snapshots", "Create & restore snapshots", "mdi6.harddisk"),
    MenuEntry(9, "Penguin's Eggs", "Create, check and install live ISOs", "ISO wizard", "mdi6.egg-outline"),
    MenuEntry(5, "Maintenance", "Clean caches, logs and system junk", "Clean caches & junk", "mdi6.broom"),
    MenuEntry(6, "Performance", "Optimize boot, swap and system responsiveness", "Boot & swap tuning", "mdi6.speedometer"),
    MenuEntry(7, "Services", "Inspect, enable and disable system services", "Systemd units", "mdi6.cog-outline"),
    MenuEntry(8, "Exit", "Exit Carbonara", "Close Carbonara", "mdi6.power"),
]


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _rgba(hex_color: str, alpha: int) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r}, {g}, {b}, {alpha}"


class TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos: QPoint | None = None

        self.setFixedHeight(42)
        self.setStyleSheet(
            """
            QWidget {
                background: #0a0a0a;
                border-bottom: 1px solid rgba(255, 255, 255, 10);
            }
            QLabel {
                color: #e4e7ec;
                background: transparent;
            }
            QPushButton {
                color: #e4e7ec;
                background: transparent;
                border: none;
                min-width: 42px;
                min-height: 30px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 14);
            }
            QPushButton#CloseButton:hover {
                background: rgba(248, 113, 113, 60);
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 10, 6)
        layout.setSpacing(8)

        self.logo = QLabel("Carbonara")
        self.logo.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
        self.logo.setAlignment(Qt.AlignCenter)

        layout.addStretch(1)
        layout.addWidget(self.logo)
        layout.addStretch(1)

        self.btn_min = QPushButton("–")
        self.btn_max = QPushButton("▢")
        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("CloseButton")

        self.btn_min.clicked.connect(self._minimize)
        self.btn_max.clicked.connect(self._toggle_max_restore)
        self.btn_close.clicked.connect(self._close)

        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

    def _window(self) -> QMainWindow | None:
        w = self.window()
        return w if isinstance(w, QMainWindow) else None

    def _minimize(self):
        win = self._window()
        if win:
            win.showMinimized()

    def _toggle_max_restore(self):
        win = self._window()
        if not win:
            return
        if win.isMaximized():
            win.showNormal()
        else:
            win.showMaximized()

    def _close(self):
        win = self._window()
        if win:
            win.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            win = self.window()
            if win and not win.isMaximized():
                win.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_max_restore()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class LogoBadge(QFrame):
    """Badge do logo Carbonara: hexágono com átomo central sobre fundo gradiente."""

    def __init__(self, size: int = 38, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {ACCENT_BLUE}, stop:1 {ACCENT_PURPLE}
                );
                border-radius: {int(size * 0.26)}px;
                border: none;
            }}
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        import math

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx, cy = self._size / 2, self._size / 2
        radius = self._size * 0.30

        # Hexágono (contorno branco semi-transparente)
        points = []
        for i in range(6):
            angle = math.radians(60 * i - 90)
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            points.append(QPointF(x, y))

        pen = QPen(QColor(255, 255, 255, 235))
        pen.setWidthF(self._size * 0.045)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(QPolygonF(points))

        # Átomo central (ponto sólido)
        dot_r = self._size * 0.075
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.drawEllipse(QPointF(cx, cy), dot_r, dot_r)


class TopHeader(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        logo_badge = LogoBadge(38)
        root.addWidget(logo_badge)

        title_block = QVBoxLayout()
        title_block.setSpacing(0)

        title_label = QLabel("Carbonara")
        title_label.setFont(QFont(FONT_FAMILY, 14, QFont.Bold))
        title_label.setStyleSheet(f"color: {TEXT};")

        sub_label = QLabel(f"{APP_VERSION} · {APP_AUTHOR}")
        sub_label.setFont(QFont(FONT_FAMILY, 9))
        sub_label.setStyleSheet(f"color: {FAINT};")

        title_block.addWidget(title_label)
        title_block.addWidget(sub_label)
        root.addLayout(title_block)

        root.addStretch()

        try:
            info = get_system_info()
        except Exception:
            info = None

        spec_items = []
        if info:
            spec_items = [
                ("CPU", info.cpu.split(" (")[0]),
                ("MEMORY", info.memory),
                ("UPTIME", info.uptime),
            ]

        for label, value in spec_items:
            cell = QVBoxLayout()
            cell.setSpacing(1)

            lbl = QLabel(label)
            lbl.setFont(QFont(FONT_FAMILY, 8, QFont.Bold))
            lbl.setStyleSheet(f"color: {FAINT}; letter-spacing: 0.5px;")
            lbl.setAlignment(Qt.AlignRight)

            val_color = ACCENT_GREEN if label == "UPTIME" else TEXT
            val = QLabel(value)
            val.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
            val.setStyleSheet(f"color: {val_color};")
            val.setAlignment(Qt.AlignRight)
            val.setWordWrap(False)

            cell.addWidget(lbl)
            cell.addWidget(val)
            root.addLayout(cell)
            root.addSpacing(20)


class GreetingBlock(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)

        import datetime
        import getpass
        hour = datetime.datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 18:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        try:
            user = getpass.getuser()
        except Exception:
            user = "there"

        title = QLabel(f"{greeting}, {user}")
        title.setFont(QFont(FONT_FAMILY, 19, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT};")

        subtitle = QLabel("Here's what's happening with your system")
        subtitle.setFont(QFont(FONT_FAMILY, 10))
        subtitle.setStyleSheet(f"color: {MUTED};")

        root.addWidget(title)
        root.addWidget(subtitle)


class HeroCard(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(150)
        self.setObjectName("HeroCard")
        self.setStyleSheet(f"""
            QFrame#HeroCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(59, 130, 246, 30),
                    stop:1 rgba(139, 92, 246, 20)
                );
                border: 1px solid rgba(99, 140, 255, 65);
                border-radius: 18px;
            }}
            QFrame#HeroCard:hover {{
                border: 1px solid rgba(99, 140, 255, 130);
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {ACCENT_GREEN}; border-radius: 4px;")
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(14)
        glow.setColor(QColor(52, 211, 153, 220))
        glow.setOffset(0, 0)
        dot.setGraphicsEffect(glow)

        status_text = QLabel("All snapshots healthy")
        status_text.setFont(QFont(FONT_FAMILY, 9, QFont.Bold))
        status_text.setStyleSheet(f"color: {ACCENT_GREEN};")

        status_row.addWidget(dot, 0, Qt.AlignVCenter)
        status_row.addWidget(status_text)
        status_row.addStretch()
        left_col.addLayout(status_row)

        title = QLabel("Timeshift")
        title.setFont(QFont(FONT_FAMILY, 18, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT};")
        left_col.addWidget(title)

        meta = QLabel("2 snapshots · last sync 14h ago")
        meta.setFont(QFont(FONT_FAMILY, 10))
        meta.setStyleSheet(f"color: {MUTED};")
        left_col.addWidget(meta)

        top_row.addLayout(left_col)
        top_row.addStretch()

        icon_badge = QLabel()
        icon_badge.setFixedSize(48, 48)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setStyleSheet("background: rgba(99,140,255,28); border-radius: 14px;")
        icon_badge.setPixmap(qta.icon("mdi6.harddisk", color=ACCENT_BLUE_LIGHT).pixmap(24, 24))
        top_row.addWidget(icon_badge, 0, Qt.AlignTop)

        root.addLayout(top_row)
        root.addStretch()

        bar_bg = QFrame()
        bar_bg.setFixedHeight(5)
        bar_bg.setStyleSheet("background: rgba(255,255,255,10); border-radius: 3px; border: none;")
        bar_fill = QFrame(bar_bg)
        bar_fill.setStyleSheet(f"""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {ACCENT_BLUE}, stop:1 {ACCENT_BLUE_LIGHT}
            );
            border-radius: 3px;
            border: none;
        """)
        self._bar_bg = bar_bg
        self._bar_fill = bar_fill
        self._fill_pct = 0.58
        root.addWidget(bar_bg)

        footer_label = QLabel("58% disk free · 217 GB available")
        footer_label.setFont(QFont(FONT_FAMILY, 9))
        footer_label.setStyleSheet(f"color: {FAINT}; margin-top: 6px;")
        root.addWidget(footer_label)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = int(self._bar_bg.width() * self._fill_pct)
        self._bar_fill.setGeometry(0, 0, w, self._bar_bg.height())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class MidCard(QFrame):
    clicked = Signal()

    def __init__(self, glyph: str, title: str, subtitle: str, badge_text: str = "", badge_color: str = "", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(150)
        self.setObjectName("MidCard")
        self.setStyleSheet(f"""
            QFrame#MidCard {{
                background: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 18px;
            }}
            QFrame#MidCard:hover {{
                background: rgba(255, 255, 255, 9);
                border: 1px solid rgba(255, 255, 255, 22);
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(0)

        icon_badge = QLabel()
        icon_badge.setFixedSize(38, 38)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setStyleSheet("background: rgba(255,255,255,8); border-radius: 11px;")
        icon_badge.setPixmap(qta.icon(glyph, color=TEXT).pixmap(18, 18))
        root.addWidget(icon_badge)
        root.addSpacing(14)

        title_label = QLabel(title)
        title_label.setFont(QFont(FONT_FAMILY, 14, QFont.Bold))
        title_label.setStyleSheet(f"color: {TEXT};")
        root.addWidget(title_label)

        sub_label = QLabel(subtitle)
        sub_label.setFont(QFont(FONT_FAMILY, 9))
        sub_label.setStyleSheet(f"color: {MUTED};")
        root.addWidget(sub_label)

        root.addStretch()

        if badge_text:
            badge = QLabel(badge_text)
            badge.setFont(QFont(FONT_FAMILY, 9, QFont.Bold))
            badge.setStyleSheet(f"""
                color: {badge_color};
                background: rgba({self._rgba(badge_color)}, 30);
                border-radius: 8px;
                padding: 4px 10px;
            """)
            badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            row = QHBoxLayout()
            row.addWidget(badge)
            row.addStretch()
            root.addLayout(row)

    @staticmethod
    def _rgba(hex_color: str) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r}, {g}, {b}"

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class SmallCard(QFrame):
    clicked = Signal(int)

    def __init__(self, entry: MenuEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(108)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._is_exit = entry.title == "Exit"
        self._apply_style()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(0)

        icon_color = ACCENT_RED if self._is_exit else TEXT
        icon_bg = "rgba(248,113,113,18)" if self._is_exit else "rgba(255,255,255,8)"

        icon_badge = QLabel()
        icon_badge.setFixedSize(32, 32)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setStyleSheet(f"background: {icon_bg}; border-radius: 9px;")
        icon_badge.setPixmap(qta.icon(entry.glyph, color=icon_color).pixmap(16, 16))
        root.addWidget(icon_badge)
        root.addSpacing(10)

        title_color = "#f0a0a0" if self._is_exit else TEXT
        title_label = QLabel(entry.title)
        title_label.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        title_label.setStyleSheet(f"color: {title_color}; background: transparent;")
        root.addWidget(title_label)

        desc_color = "#8a5a5a" if self._is_exit else FAINT
        desc_label = QLabel(entry.short_desc)
        desc_label.setFont(QFont(FONT_FAMILY, 9))
        desc_label.setStyleSheet(f"color: {desc_color}; background: transparent;")
        root.addWidget(desc_label)

    def _apply_style(self):
        self.setObjectName("SmallCard")
        if self._is_exit:
            bg = "rgba(248, 113, 113, 8)"
            border = "1px solid rgba(248, 113, 113, 35)"
            hover_border = "1px solid rgba(248, 113, 113, 80)"
        else:
            bg = "rgba(255, 255, 255, 6)"
            border = "1px solid rgba(255, 255, 255, 12)"
            hover_border = "1px solid rgba(255, 255, 255, 24)"

        self.setStyleSheet(f"""
            QFrame#SmallCard {{
                background: {bg};
                border: {border};
                border-radius: 16px;
            }}
            QFrame#SmallCard:hover {{
                border: {hover_border};
            }}
            QFrame#SmallCard QLabel {{
                border: none;
            }}
        """)

    def set_active(self, value: bool):
        self.active = value
        if value:
            accent = ACCENT_RED if self._is_exit else ACCENT_BLUE_LIGHT
            self.setStyleSheet(f"""
                QFrame#SmallCard {{
                    background: rgba(255, 255, 255, 12);
                    border: 1px solid {accent};
                    border-radius: 16px;
                }}
                QFrame#SmallCard QLabel {{
                    border: none;
                }}
            """)
        else:
            self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.entry.number)
            event.accept()
            return
        super().mousePressEvent(event)


class BackupsHost(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QWidget { background: transparent; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(0)
        self.page = BackupsPage(self)
        root.addWidget(self.page, 1)


class EggsHost(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QWidget { background: transparent; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(0)
        self.page = EggsPage(self)
        root.addWidget(self.page, 1)


class DisksHost(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QWidget { background: transparent; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(0)
        self.page = DisksPage(self)
        root.addWidget(self.page, 1)


class ExitConfirmDialog(QDialog):
    """
    Dialog modal de confirmação de saída.

    Implementado como QDialog (não QFrame solto) porque QDialog é o
    mecanismo nativo do Qt para janelas modais — ele garante que a
    superfície de renderização seja alocada e pintada corretamente desde
    a primeira chamada de exec()/show(), sem o problema de widgets soltos
    fora de qualquer layout só renderizarem após um repaint global da
    árvore (o que causava o overlay anterior "não aparecer" no primeiro
    ESC pressionado após abrir o app).
    """

    confirmed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Cobre a janela pai inteira com um overlay escuro
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignCenter)

        self.card = QFrame(self)
        self.card.setObjectName("ExitConfirmCard")
        self.card.setFixedSize(400, 220)
        self.card.setStyleSheet(f"""
            QFrame#ExitConfirmCard {{
                background: #14151c;
                border: 1px solid rgba(248, 113, 113, 60);
                border-radius: 18px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(0)

        icon_badge = QLabel()
        icon_badge.setFixedSize(44, 44)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setStyleSheet(f"background: rgba({_rgba(ACCENT_RED, 18)}); border-radius: 13px;")
        icon_badge.setPixmap(qta.icon("mdi6.power", color=ACCENT_RED).pixmap(22, 22))
        card_layout.addWidget(icon_badge)
        card_layout.addSpacing(18)

        title = QLabel("Exit Carbonara?")
        title.setFont(QFont(FONT_FAMILY, 15, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT};")
        card_layout.addWidget(title)
        card_layout.addSpacing(8)

        subtitle = QLabel("Any unsaved progress in the current view will be lost.")
        subtitle.setFont(QFont(FONT_FAMILY, 10))
        subtitle.setStyleSheet(f"color: {MUTED}; line-height: 140%;")
        subtitle.setWordWrap(True)
        card_layout.addWidget(subtitle)
        card_layout.addStretch()
        card_layout.addSpacing(22)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(40)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,14);
                border-radius: 10px;
                color: {TEXT};
                font-family: "{FONT_FAMILY}";
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,14);
            }}
        """)
        btn_cancel.clicked.connect(self.reject)

        btn_exit = QPushButton("Exit")
        btn_exit.setFixedHeight(40)
        btn_exit.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_RED};
                border: none;
                border-radius: 10px;
                color: #1a0a0a;
                font-family: "{FONT_FAMILY}";
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #ff8a8a;
            }}
        """)
        btn_exit.clicked.connect(self._on_confirm)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_exit)
        card_layout.addLayout(btn_row)

        outer.addWidget(self.card)

    def _on_confirm(self):
        self.confirmed.emit()
        self.accept()

    def paintEvent(self, event):
        # Pinta o overlay escuro semi-transparente cobrindo toda a área
        # do dialog (que por sua vez cobre a janela pai inteira).
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_confirm()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        # Clique fora do card (na área do overlay) cancela
        if not self.card.geometry().contains(event.pos()):
            self.reject()
            return
        super().mousePressEvent(event)


class MenuPage(QWidget):
    backups_requested = Signal()
    eggs_requested = Signal()
    disks_requested = Signal()
    exit_requested = Signal()
    exit_requested_confirm = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_index = 0
        self.small_cards: list[SmallCard] = []

        self.setStyleSheet(
            f"""
            QWidget {{
                background: transparent;
            }}
            QFrame {{
                background: transparent;
            }}
            QLineEdit {{
                color: {TEXT};
                background: transparent;
                border: none;
                padding: 0px;
            }}
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(22)
        outer.setAlignment(Qt.AlignTop)

        self.header = TopHeader()
        outer.addWidget(self.header)

        self.greeting = GreetingBlock()
        outer.addWidget(self.greeting)

        hero_row = QHBoxLayout()
        hero_row.setSpacing(14)

        self.hero_backups = HeroCard()
        self.hero_backups.clicked.connect(self.backups_requested.emit)
        hero_row.addWidget(self.hero_backups, 14)

        self.mid_packages = MidCard(
            "mdi6.package-variant", "Packages", "Mirrors & updates",
            badge_text="12 updates", badge_color=ACCENT_AMBER,
        )
        self.mid_packages.clicked.connect(lambda: self._go_to(3))
        hero_row.addWidget(self.mid_packages, 10)

        self.mid_services = MidCard(
            "mdi6.cog-outline", "Services", "Systemd units",
            badge_text="1 failed", badge_color=ACCENT_RED,
        )
        self.mid_services.clicked.connect(lambda: self._go_to(7))
        hero_row.addWidget(self.mid_services, 10)

        outer.addLayout(hero_row)

        small_entries = [e for e in MENU_ENTRIES if e.number not in (4,)]
        grid = QGridLayout()
        grid.setSpacing(12)

        for i, entry in enumerate(small_entries):
            card = SmallCard(entry)
            card.clicked.connect(self._on_card_clicked)
            self.small_cards.append(card)
            row, col = divmod(i, 5)
            grid.addWidget(card, row, col)

        outer.addLayout(grid)
        outer.addStretch()

        self.footer = QFrame()
        self.footer.setStyleSheet("""
            QFrame {
                border: 1px solid rgba(255,255,255,12);
                border-radius: 14px;
                background: rgba(255,255,255,4);
            }
        """)
        self.footer.setFixedHeight(56)

        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(18, 8, 18, 8)
        footer_layout.setSpacing(8)

        self.prompt = QLabel("❯")
        self.prompt.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        self.prompt.setStyleSheet(f"color: {ACCENT_BLUE_LIGHT}; background: transparent; border: none;")

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type a number, or click a card...")
        self.input_box.setFont(QFont(FONT_FAMILY, 11))
        self.input_box.setStyleSheet(f"""
            QLineEdit {{
                color: {TEXT};
                background: transparent;
                border: none;
                padding: 0px;
            }}
        """)
        self.input_box.installEventFilter(self)

        footer_layout.addWidget(self.prompt)
        footer_layout.addWidget(self.input_box, 1)
        outer.addWidget(self.footer)

        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont(FONT_FAMILY, 9))
        self.status.setStyleSheet(f"color: {FAINT}; background: transparent; border: none;")
        outer.addWidget(self.status)

        self.input_box.setFocus()
        self._refresh_selection()

    def _request_exit(self):
        self.exit_requested_confirm.emit()

    def _go_to(self, number: int):
        self._on_card_clicked(number)

    def _index_of(self, number: int) -> int:
        small_entries = [e for e in MENU_ENTRIES if e.number not in (4,)]
        for idx, entry in enumerate(small_entries):
            if entry.number == number:
                return idx
        return -1

    def _refresh_selection(self):
        for i, card in enumerate(self.small_cards):
            card.set_active(i == self.current_index)

    def _on_card_clicked(self, number: int):
        idx = self._index_of(number)
        if idx >= 0:
            self.current_index = idx
            self._refresh_selection()
        self._confirm(number)

    def _move(self, step: int):
        if not self.small_cards:
            return
        self.current_index = (self.current_index + step) % len(self.small_cards)
        self._refresh_selection()
        entry = self.small_cards[self.current_index].entry
        self.status.setText(f"Selected: {entry.number} — {entry.title}")

    def _confirm_current(self):
        if not self.small_cards:
            return
        entry = self.small_cards[self.current_index].entry
        self._confirm(entry.number)

    def _confirm(self, number: int):
        entry = next((e for e in MENU_ENTRIES if e.number == number), None)
        if entry is None:
            return
        self.status.setText(f"Confirmed: {entry.number} — {entry.title}")

        if entry.number == 1:
            self.disks_requested.emit()
            return
        if entry.number == 4:
            self.backups_requested.emit()
            return
        if entry.number == 9:
            self.eggs_requested.emit()
            return
        if entry.title == "Exit":
            self.exit_requested.emit()

    def _accept_typed_choice(self):
        text = self.input_box.text().strip()
        if not text.isdigit():
            self.status.setText("Type only a number from the menu.")
            self.input_box.selectAll()
            return

        choice = int(text)
        entry = next((e for e in MENU_ENTRIES if e.number == choice), None)
        if entry is None:
            self.status.setText(f"Invalid choice: {choice}")
            self.input_box.selectAll()
            return

        idx = self._index_of(choice)
        if idx >= 0:
            self.current_index = idx
            self._refresh_selection()
        self.input_box.clear()
        self._confirm(choice)

    def eventFilter(self, obj, event):
        if obj is self.input_box and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Up, Qt.Key_W):
                self._move(-1)
                return True
            if key in (Qt.Key_Down, Qt.Key_S):
                self._move(1)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._accept_typed_choice()
                return True
            if key == Qt.Key_Escape:
                self._request_exit()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_W):
            self._move(-1)
            return
        if key in (Qt.Key_Down, Qt.Key_S):
            self._move(1)
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._confirm_current()
            return
        if key == Qt.Key_Escape:
            self._request_exit()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Carbonara")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.resize(1280, 900)
        self.setMinimumSize(1100, 780)
        self.setStyleSheet(f"background: {BG};")

        central = QWidget(self)
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar(self)
        self.stack = QStackedWidget(self)

        self.menu_page = MenuPage(self)
        self.backups_host = BackupsHost(self)
        self.eggs_host = EggsHost(self)
        self.disks_host = DisksHost(self)

        self.stack.addWidget(self.menu_page)
        self.stack.addWidget(self.backups_host)
        self.stack.addWidget(self.eggs_host)
        self.stack.addWidget(self.disks_host)

        root.addWidget(self.titlebar)
        root.addWidget(self.stack, 1)

        self.menu_page.backups_requested.connect(self.show_backups)
        self.menu_page.eggs_requested.connect(self.show_eggs)
        self.menu_page.disks_requested.connect(self.show_disks)
        self.menu_page.exit_requested.connect(self.close)
        self.menu_page.exit_requested_confirm.connect(self._show_exit_dialog)
        self.backups_host.page.back_requested.connect(self.show_menu)
        self.eggs_host.page.back_requested.connect(self.show_menu)
        self.disks_host.page.back_requested.connect(self.show_menu)

        self.stack.setCurrentWidget(self.menu_page)

    def _show_exit_dialog(self):
        dialog = ExitConfirmDialog(self)
        dialog.setGeometry(self.geometry())
        dialog.confirmed.connect(self.close)
        dialog.exec()
        if self.stack.currentWidget() is self.menu_page:
            self.menu_page.input_box.setFocus()

    def show_menu(self):
        self.stack.setCurrentWidget(self.menu_page)
        self.menu_page.input_box.setFocus()

    def show_backups(self):
        self.stack.setCurrentWidget(self.backups_host)

    def show_eggs(self):
        self.stack.setCurrentWidget(self.eggs_host)

    def show_disks(self):
        self.stack.setCurrentWidget(self.disks_host)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape and self.stack.currentWidget() in (
            self.backups_host, self.eggs_host, self.disks_host
        ):
            self.show_menu()
            return
        super().keyPressEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont(FONT_FAMILY, 10))

    win = MainWindow()
    win.show()
    win.raise_()
    win.activateWindow()
    win.menu_page.input_box.setFocus()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
