from __future__ import annotations

import os

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QPushButton,
    QDialog,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
)


class _CloseLabel(QLabel):
    """'X' de fechar clicável, no mesmo padrão visual usado nos outros dialogs."""

    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setFixedSize(24, 24)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QLabel { color: #9aa6b2; font-size: 13px; border-radius: 6px; }"
            "QLabel:hover { background: rgba(200,60,60,60); color: #ff8888; }"
        )


class _ErrorDialog(QDialog):
    """Dialog de erro estilizado (dark, tema vermelho) — substitui o
    QMessageBox.warning() genérico do sistema, que destoa do resto da UI."""

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
        icon.setPixmap(qta.icon("mdi6.alert-circle", color="#ff8888").pixmap(16, 16))
        icon.setStyleSheet("QLabel { background: rgba(220,80,80,40); border-radius: 7px; }")

        lbl = QLabel(title)
        lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
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
                background: rgba(220, 80, 80, 35);
                border-bottom: 1px solid rgba(220, 80, 80, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#ErrBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#ErrBtnOk {
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(220, 80, 80, 120);
                border-radius: 8px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px; padding: 5px 0;
            }
            QPushButton#ErrBtnOk:hover {
                background: rgba(220, 80, 80, 40);
                border-color: rgba(255, 120, 120, 200);
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


class _StatCard(QFrame):
    """Card de resumo (somente leitura) para a faixa de status do topo."""

    def __init__(
        self,
        label: str,
        value: str,
        color: str = "#dce6f0",
        parent=None,
        glyph: str = "mdi6.information-outline",
        bar_color: str = "#23a6ff",
        is_status: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("EggsStatCard")
        self.setFixedHeight(96)
        self._glyph = glyph
        self._is_status = is_status
        self.setStyleSheet(f"""
            QFrame#EggsStatCard {{
                background: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 8);
                border-top: 2px solid {bar_color};
                border-radius: 14px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 35))
        self.setGraphicsEffect(shadow)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)
        outer.setAlignment(Qt.AlignVCenter)

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(34, 34)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setPixmap(qta.icon(glyph, color=bar_color).pixmap(18, 18))
        h = bar_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        self.icon_lbl.setStyleSheet(
            f"QLabel {{ background: rgba({r},{g},{b},30); border-radius: 10px; }}"
        )

        text_col = QVBoxLayout()
        text_col.setSpacing(6)
        text_col.setAlignment(Qt.AlignVCenter)

        lbl = QLabel(label)
        lbl.setFont(QFont("DejaVu Sans Mono", 9))
        lbl.setStyleSheet("color: #6b7a8d; background: transparent; border: none;")

        value_row = QHBoxLayout()
        value_row.setSpacing(6)
        value_row.setContentsMargins(0, 0, 0, 0)

        self.dot_lbl = QLabel("●")
        self.dot_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none; font-size: 10px;")
        self.dot_lbl.setVisible(is_status)

        self.value_lbl = QLabel(value)
        self.value_lbl.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
        self.value_lbl.setWordWrap(True)
        self.value_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")

        value_row.addWidget(self.dot_lbl)
        value_row.addWidget(self.value_lbl, 1)

        text_col.addWidget(lbl)
        text_col.addLayout(value_row)

        outer.addWidget(self.icon_lbl)
        outer.addLayout(text_col, 1)

    def set_value(self, value: str, color: str | None = None) -> None:
        self.value_lbl.setText(value)
        if color:
            self.value_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            self.dot_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none; font-size: 10px;")


class _EggsOptionButton(QFrame):
    """Card de ação clicável, no mesmo padrão visual dos cards de Restore."""

    clicked = Signal()

    def __init__(
        self,
        glyph: str,
        title: str,
        desc: str,
        color: str,
        parent=None,
        badge: str = "",
        primary: bool = False,
    ):
        super().__init__(parent)
        self._color = color
        self._primary = primary
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("EggsOptionBtn")
        self.setFixedHeight(130 if primary else 110)

        bg = "rgba(255, 255, 255, 9)" if primary else "rgba(255, 255, 255, 5)"
        border = f"1px solid {color}" if primary else "1px solid rgba(255, 255, 255, 10)"
        self.setStyleSheet(f"""
            QFrame#EggsOptionBtn {{
                background: {bg};
                border: {border};
                border-radius: 18px;
            }}
            QFrame#EggsOptionBtn:hover {{
                background: rgba(255, 255, 255, 12);
                border: 1px solid {color};
            }}
            QFrame#EggsOptionBtn:disabled {{
                background: rgba(255, 255, 255, 2);
                border: 1px solid rgba(255, 255, 255, 6);
            }}
        """)

        # Sombra de profundidade — card primário ganha um glow sutil na
        # cor de destaque, os demais uma sombra neutra discreta.
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(28 if primary else 18)
        self._shadow.setOffset(0, 2 if primary else 0)
        if primary:
            h = color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            self._shadow.setColor(QColor(r, g, b, 90))
        else:
            self._shadow.setColor(QColor(0, 0, 0, 35))
        self.setGraphicsEffect(self._shadow)
        self._shadow_blur_base = self._shadow.blurRadius()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignVCenter)

        icon_size = 56 if primary else 48
        glyph_size = 28
        ico_lbl = QLabel()
        ico_lbl.setFixedSize(icon_size, icon_size)
        ico_lbl.setAlignment(Qt.AlignCenter)
        ico_lbl.setPixmap(qta.icon(glyph, color=color).pixmap(glyph_size, glyph_size))
        h = color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        ico_lbl.setStyleSheet(
            f"QLabel {{ background: rgba({r},{g},{b},40); "
            f"border-radius: 14px; border: 1px solid rgba({r},{g},{b},90); }}"
        )

        text = QVBoxLayout()
        text.setSpacing(4)
        text.setContentsMargins(0, 0, 0, 0)
        text.setAlignment(Qt.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel(title)
        self.title_lbl.setFont(QFont("DejaVu Sans Mono", 13 if primary else 12, QFont.Bold))
        self.title_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        title_row.addWidget(self.title_lbl)

        self.badge_lbl = None
        if badge:
            badge_lbl = QLabel(badge.upper())
            badge_lbl.setFont(QFont("DejaVu Sans Mono", 8, QFont.Bold))
            # Badge discreta — cinza neutro em vez da cor de destaque do
            # card, pra não competir visualmente com o título.
            badge_lbl.setStyleSheet(
                "color: #6b7a8d; background: rgba(255,255,255,10); "
                "border: 1px solid rgba(255,255,255,18); border-radius: 5px; "
                "padding: 2px 7px;"
            )
            title_row.addWidget(badge_lbl)
            self.badge_lbl = badge_lbl

        title_row.addStretch()

        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setFont(QFont("DejaVu Sans Mono", 10.5))
        self.desc_lbl.setWordWrap(False)
        self.desc_lbl.setStyleSheet("color: #7d8a99; background: transparent; border: none;")

        text.addLayout(title_row)
        text.addWidget(self.desc_lbl)

        if primary:
            cta_row = QHBoxLayout()
            cta_row.setContentsMargins(0, 4, 0, 0)
            cta = QLabel(f"▸ {title.split()[0]} ISO")
            cta.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
            cta.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            cta_row.addStretch()
            cta_row.addWidget(cta)
            text.addLayout(cta_row)

        layout.addWidget(ico_lbl, 0, Qt.AlignVCenter)
        layout.addLayout(text)
        layout.addStretch()

    def set_title(self, title: str) -> None:
        self.title_lbl.setText(title)

    def set_desc(self, desc: str) -> None:
        self.desc_lbl.setText(desc)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def enterEvent(self, event):
        # Hover "moderno" (estilo GNOME Software): intensifica a sombra
        # em vez de mover pixels de verdade — é mais robusto dentro de um
        # QGridLayout do que tentar deslocar a posição do widget.
        anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        anim.setDuration(150)
        anim.setStartValue(self._shadow.blurRadius())
        anim.setEndValue(self._shadow_blur_base + 14)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._hover_anim = anim
        super().enterEvent(event)

    def leaveEvent(self, event):
        anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        anim.setDuration(150)
        anim.setStartValue(self._shadow.blurRadius())
        anim.setEndValue(self._shadow_blur_base)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._hover_anim = anim
        super().leaveEvent(event)


class EggsPage(QWidget):
    """Tela do Penguin's Eggs Wizard — criação, checagem e instalação de ISOs."""

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Mesmo mecanismo do Create Snapshot: Popen direto na thread
        # principal + QTimer de polling, sem QThread própria — elimina
        # qualquer diferença arquitetural entre as duas telas.
        self._proc = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(300)
        self._poll_timer.timeout.connect(self._poll_process)

        # Auto-refresh das stats do topo (Última ISO, Ventoy, Instalado) —
        # só roda enquanto a tela está de fato visível (liga no showEvent,
        # desliga no hideEvent), pra não ficar varrendo o Ventoy e chamando
        # pacman em segundo plano quando o usuário está em outra tela.
        self._stats_refresh_timer = QTimer(self)
        self._stats_refresh_timer.setInterval(8000)
        self._stats_refresh_timer.timeout.connect(self.refresh_stats)

        # Garante que nenhum pkexec fique órfão rodando em segundo plano
        # se o app for fechado com uma operação (Create/Check/Install)
        # ainda em andamento.
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._terminate_pending_operation)

        self.setStyleSheet(
            """
            QWidget { background: transparent; }
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
            QPushButton#BackLink {
                padding: 4px 2px;
                border: none;
                background: transparent;
                color: #9aa6b2;
                text-align: left;
            }
            QPushButton#BackLink:hover {
                background: transparent;
                border: none;
                color: #23a6ff;
            }
            """
        )
        self._build_ui()

    def _build_ui(self) -> None:
        from ui.main_window import TopHeader  # import adiado — evita import circular

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 18, 32, 24)
        root.setSpacing(16)

        self.top_header = TopHeader()
        root.addWidget(self.top_header)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)

        # Item 10 — parece navegação (só texto, sem moldura de botão),
        # em vez de um botão comum.
        btn_back = QPushButton("←  Back")
        btn_back.setObjectName("BackLink")
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.clicked.connect(self.back_requested.emit)
        top_row.addWidget(btn_back)
        top_row.addStretch(1)

        root.addLayout(top_row)

        # ── Header ───────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet("background: transparent; border: none;")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)

        icon = QLabel()
        icon.setFixedSize(38, 38)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.egg-outline", color="#23a6ff").pixmap(24, 24))
        icon.setStyleSheet(
            "QLabel { background: rgba(35,166,255,30); border-radius: 10px; }"
        )

        title = QLabel("Penguin's Eggs")
        title.setFont(QFont("DejaVu Sans Mono", 22, QFont.Bold))
        title.setStyleSheet("color: #23a6ff;")

        title_row.addWidget(icon)
        title_row.addWidget(title)
        title_row.addStretch()

        subtitle = QLabel("Create, verify and deploy Arch Linux Live ISOs")
        subtitle.setFont(QFont("DejaVu Sans Mono", 10))
        subtitle.setStyleSheet("color: #9aa6b2;")

        h_layout.addLayout(title_row)
        h_layout.addWidget(subtitle)

        # ── Faixa de status ──────────────────────────────────────────────
        from core.eggs.eggs import get_dashboard_stats

        stats = get_dashboard_stats()

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self.stat_last_iso = _StatCard(
            "ÚLTIMA ISO", stats["last_iso"] or "nenhuma gerada",
            glyph="mdi6.file-multiple-outline", bar_color="#23a6ff",
        )
        self.stat_ventoy = _StatCard(
            "VENTOY",
            f"{stats['ventoy_free_gb']:.1f} GB livres" if stats["ventoy_free_gb"] is not None else "não montado",
            color="#9bf0bd" if stats["ventoy_free_gb"] is not None else "#6b7a8d",
            glyph="mdi6.usb-flash-drive-outline", bar_color="#9bf0bd",
        )
        self.stat_installed = _StatCard(
            "PENGUINS-EGGS",
            "Instalado" if stats["eggs_installed"] else "Não instalado",
            color="#9bf0bd" if stats["eggs_installed"] else "#ffb86b",
            glyph="mdi6.check-decagram-outline", bar_color="#ffb86b",
            is_status=True,
        )

        stats_row.addWidget(self.stat_last_iso, 1)
        stats_row.addWidget(self.stat_ventoy, 1)
        stats_row.addWidget(self.stat_installed, 1)

        # ── Cards de ação ────────────────────────────────────────────────
        cards = QGridLayout()
        cards.setSpacing(12)
        cards.setColumnStretch(0, 1)
        cards.setColumnStretch(1, 1)

        self.btn_create = _EggsOptionButton(
            glyph="mdi6.egg-easter",
            title="Create Penguin's Eggs",
            desc="Gera uma nova ISO live (ou move uma já pronta para o Ventoy).",
            color="#9bf0bd",
            parent=self,
            badge="root",
            primary=True,
        )
        self.btn_create.clicked.connect(self._on_create)

        self.btn_check = _EggsOptionButton(
            glyph="mdi6.file-search-outline",
            title="Check Penguin's Eggs .iso",
            desc="Verifica se há uma .iso pendente e move/faz backup automaticamente.",
            color="#23a6ff",
            parent=self,
            badge="root",
        )
        self.btn_check.clicked.connect(self._on_check)

        self.btn_broot = _EggsOptionButton(
            glyph="mdi6.folder-search-outline",
            title="Open files — broot",
            desc="Abre o diretório do Ventoy (destino final da ISO) no broot.",
            color="#c8a2ff",
            parent=self,
        )
        self.btn_broot.clicked.connect(lambda: self._open_files("broot"))

        self.btn_nautilus = _EggsOptionButton(
            glyph="mdi6.folder-open-outline",
            title="Open files — Nautilus",
            desc="Abre o diretório do Ventoy (destino final da ISO) no Nautilus.",
            color="#ffb86b",
            parent=self,
        )
        self.btn_nautilus.clicked.connect(lambda: self._open_files("nautilus"))

        # Item 13 — o card de instalação muda de texto sozinho conforme o
        # penguins-eggs já estar instalado ou não.
        install_title, install_desc = self._install_card_texts(stats["eggs_installed"])
        self.btn_install = _EggsOptionButton(
            glyph="mdi6.download-circle-outline",
            title=install_title,
            desc=install_desc,
            color="#ff9966",
            parent=self,
            badge="root",
        )
        self.btn_install.clicked.connect(self._on_install)

        cards.addWidget(self.btn_create, 0, 0, 1, 2)
        cards.addWidget(self.btn_check, 1, 0)
        cards.addWidget(self.btn_install, 1, 1)
        cards.addWidget(self.btn_broot, 2, 0)
        cards.addWidget(self.btn_nautilus, 2, 1)

        # Envolve cada grupo (header, faixa de status, cards) num QWidget
        # próprio — necessário pra poder animar opacidade em grupo com
        # QGraphicsOpacityEffect (item 14, fade-in escalonado ao abrir).
        stats_widget = QWidget()
        stats_widget.setLayout(stats_row)

        cards_widget = QWidget()
        cards_widget.setLayout(cards)

        root.addWidget(header)
        root.addWidget(stats_widget)
        root.addSpacing(12)
        root.addWidget(cards_widget)
        root.addStretch(1)

        self._animate_entrance(
            header_widgets=[self.top_header, header],
            reveal_widgets=[stats_widget, cards_widget],
        )

    def _animate_entrance(self, header_widgets: list[QWidget], reveal_widgets: list[QWidget]) -> None:
        """Fade-in escalonado ao abrir a tela.

        header_widgets: aparecem com fade suave via QGraphicsOpacityEffect
        (seguro aqui porque não têm filhos com efeito gráfico próprio).

        reveal_widgets: os cards de status/ação têm filhos com seu próprio
        QGraphicsDropShadowEffect — no Qt, aninhar um QGraphicsOpacityEffect
        num widget-pai cujos filhos já têm efeito próprio faz os filhos
        simplesmente não serem desenhados. Por isso esses grupos usam um
        "aparecer" simples (setVisible escalonado) em vez de fade aninhado.
        """
        self._entrance_anims = []  # mantém referência viva (senão o GC mata a animação no meio)

        delay = 0
        for w in header_widgets:
            effect = QGraphicsOpacityEffect(w)
            effect.setOpacity(0.0)
            w.setGraphicsEffect(effect)

            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(180)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._entrance_anims.append((effect, anim))
            QTimer.singleShot(delay, anim.start)
            delay += 90

        for w in reveal_widgets:
            w.setVisible(False)
            QTimer.singleShot(delay, lambda w=w: w.setVisible(True))
            delay += 90

    def _install_card_texts(self, installed: bool) -> tuple[str, str]:
        """Item 13 — o card de instalação muda de texto sozinho conforme
        o penguins-eggs já estar instalado ou não."""
        if installed:
            return (
                "Update Penguin's Eggs",
                "Atualiza o penguins-eggs e o módulo Calamares para a versão mais recente.",
            )
        return (
            "Penguin's Eggs and Calamares Install",
            "Instala o penguins-eggs e o módulo Calamares, se necessário.",
        )

    def refresh_stats(self) -> None:
        from core.eggs.eggs import get_dashboard_stats

        stats = get_dashboard_stats()
        self.stat_last_iso.set_value(stats["last_iso"] or "nenhuma gerada")
        self.stat_ventoy.set_value(
            f"{stats['ventoy_free_gb']:.1f} GB livres" if stats["ventoy_free_gb"] is not None else "não montado",
            color="#9bf0bd" if stats["ventoy_free_gb"] is not None else "#6b7a8d",
        )
        self.stat_installed.set_value(
            "Instalado" if stats["eggs_installed"] else "Não instalado",
            color="#9bf0bd" if stats["eggs_installed"] else "#ffb86b",
        )
        install_title, install_desc = self._install_card_texts(stats["eggs_installed"])
        self.btn_install.set_title(install_title)
        self.btn_install.set_desc(install_desc)

    # ── Ações ────────────────────────────────────────────────────────────

    def _terminate_pending_operation(self) -> None:
        """Mata qualquer pkexec ainda em andamento — chamado ao fechar o
        app inteiro (aboutToQuit). Sem isso, fechar o Carbonara no meio
        de um Create/Check/Install deixava o processo órfão rodando pra
        sempre, acumulando a cada tentativa abandonada."""
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _run_with_progress(self, func_name: str, dialog_title: str, preparing_text: str = "Aguardando...", icon_glyph: str = "mdi6.egg-outline") -> None:
        # Evita disparar uma segunda execução em paralelo se o usuário
        # clicar de novo enquanto o pkexec ainda está subindo.
        if self._proc is not None and self._proc.poll() is None:
            return

        import json
        import subprocess

        args_json = json.dumps({
            "func_name": func_name,
            "title": dialog_title,
            "preparing_text": preparing_text,
            "icon_glyph": icon_glyph,
        })

        cmd = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "eggs_action",
            args_json,
        ]

        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        except Exception as exc:
            _show_error("Penguin's Eggs", f"Erro ao executar:\n\n{exc}", parent=self)
            return

        self._set_cards_enabled(False)
        self._poll_timer.start()

    def _poll_process(self) -> None:
        if self._proc is None:
            return

        rc = self._proc.poll()
        if rc is None:
            return  # ainda rodando

        self._poll_timer.stop()
        try:
            stdout, stderr = self._proc.communicate()
        except Exception:
            stdout, stderr = "", ""
        self._proc = None

        self._set_cards_enabled(True)
        self.refresh_stats()

        output = stderr or stdout or ""
        if rc == 126 or "dismissed" in output.lower():
            return
        if rc != 0:
            err = (output or f"exit code {rc}").strip()
            _show_error("Penguin's Eggs", f"Erro ao executar:\n\n{err}", parent=self)

    def _set_cards_enabled(self, enabled: bool) -> None:
        """Desabilita visualmente os cards de ação enquanto uma operação
        pkexec está em andamento — dá feedback imediato de que o clique
        já registrou, evitando que o usuário clique de novo achando que
        não funcionou durante o delay de abertura do prompt de senha."""
        for btn in (self.btn_create, self.btn_check, self.btn_install):
            btn.setEnabled(enabled)

    def _on_create(self) -> None:
        self._run_with_progress("create_eggs", "Criando Penguin's Eggs...", "Criando ISO...", "mdi6.egg-easter")

    def _on_check(self) -> None:
        self._run_with_progress("check_eggs", "Verificando Penguin's Eggs...", "Verificando .iso...", "mdi6.file-search-outline")

    def _on_install(self) -> None:
        self._run_with_progress("install_eggs", "Instalando Penguin's Eggs...", "Instalando...", "mdi6.download-circle-outline")

    def _open_files(self, kind: str) -> None:
        from core.eggs.eggs import open_file_manager
        try:
            open_file_manager(kind)
        except Exception as exc:  # noqa: BLE001
            _show_error("Penguin's Eggs", f"Não foi possível abrir: {exc}", parent=self)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.back_requested.emit()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        # Recalcula na hora que a tela aparece (cobre o caso de ter saído
        # e voltado), e liga o auto-refresh periódico enquanto estiver
        # visível.
        self.refresh_stats()
        self._stats_refresh_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._stats_refresh_timer.stop()
        super().hideEvent(event)
