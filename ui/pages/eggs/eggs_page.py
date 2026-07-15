from __future__ import annotations

import os

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QPushButton,
    QDialog,
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


class _VentoyCard(QFrame):
    """Card do Ventoy no mesmo estilo do card de destino do Timeshift —
    ícone, título + detalhes, barra de progresso com % livre."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VentoyCard")
        self.setStyleSheet("""
            QFrame#VentoyCard {
                background: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 8);
                border-radius: 14px;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(44, 44)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setPixmap(qta.icon("mdi6.usb-flash-drive-outline", color="#9bf0bd").pixmap(20, 20))
        self.icon_lbl.setStyleSheet(
            "QLabel { background: rgba(255,255,255,6); border-radius: 10px; }"
        )

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_lbl = QLabel("VENTOY")
        title_lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        title_lbl.setStyleSheet("color: #ecf4ff; background: transparent; border: none;")

        self.detail_lbl = QLabel("não montado")
        self.detail_lbl.setFont(QFont("DejaVu Sans Mono", 9))
        self.detail_lbl.setStyleSheet("color: #7d8a99; background: transparent; border: none;")

        text_col.addWidget(title_lbl)
        text_col.addWidget(self.detail_lbl)

        top_row.addWidget(self.icon_lbl)
        top_row.addLayout(text_col, 1)

        bar_wrap = QHBoxLayout()
        bar_wrap.setSpacing(10)

        self.bar_track = QFrame()
        self.bar_track.setFixedHeight(5)
        self.bar_track.setStyleSheet(
            "QFrame { background: rgba(255,255,255,10); border-radius: 3px; border: none; }"
        )
        self.bar_fill = QFrame(self.bar_track)
        self.bar_fill.setStyleSheet(
            "QFrame { background: #23a6ff; border-radius: 3px; border: none; }"
        )
        self.bar_fill.setGeometry(0, 0, 0, 5)

        self.pct_lbl = QLabel("—")
        self.pct_lbl.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        self.pct_lbl.setStyleSheet("color: #5eea95; background: transparent; border: none;")
        self.pct_lbl.setFixedWidth(85)
        self.pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        bar_wrap.addWidget(self.bar_track, 1)
        bar_wrap.addWidget(self.pct_lbl)

        outer.addLayout(top_row)
        outer.addLayout(bar_wrap)

    def set_stats(
        self,
        free_gb: float | None,
        total_gb: float | None,
        fs_type: str | None,
        free_pct: int | None = None,
    ) -> None:
        if free_gb is None or total_gb is None or total_gb <= 0:
            self.detail_lbl.setText("não montado")
            self.pct_lbl.setText("—")
            self.bar_fill.setGeometry(0, 0, 0, 5)
            return

        # Usa a porcentagem calculada pelo próprio `df` (idêntica ao que
        # `df -h` mostra no terminal) — só recalcula por conta própria se,
        # por algum motivo, ela não tiver vindo preenchida.
        pct_free = free_pct if free_pct is not None else (free_gb / total_gb) * 100
        fs = fs_type or "?"
        self.detail_lbl.setText(
            f"{free_gb:.1f} GB livres de {total_gb:.1f} GB  •  /mnt/VENTOY  •  {fs}"
        )
        self.pct_lbl.setText(f"{pct_free:.0f}% livre")

        track_width = self.bar_track.width() or 200
        fill_width = int(track_width * min(max(pct_free / 100, 0), 1))
        self.bar_fill.setGeometry(0, 0, fill_width, 5)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Recalcula a largura da barra preenchida proporcionalmente ao
        # redimensionar a tela.
        text = self.pct_lbl.text()
        if text != "—" and text.endswith("% livre"):
            try:
                pct = float(text.replace("% livre", ""))
                fill_width = int(self.bar_track.width() * min(max(pct / 100, 0), 1))
                self.bar_fill.setGeometry(0, 0, fill_width, self.bar_track.height())
            except ValueError:
                pass


class _StatCard(QFrame):
    """Card de resumo (somente leitura) para a faixa de status do topo."""

    def __init__(self, label: str, value: str, color: str = "#dce6f0", parent=None):
        super().__init__(parent)
        self.setObjectName("EggsStatCard")
        self.setFixedHeight(96)
        self.setStyleSheet("""
            QFrame#EggsStatCard {
                background: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 8);
                border-radius: 18px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignVCenter)

        lbl = QLabel(label)
        lbl.setFont(QFont("DejaVu Sans Mono", 9))
        lbl.setStyleSheet("color: #6b7a8d; background: transparent; border: none;")

        self.value_lbl = QLabel(value)
        self.value_lbl.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
        self.value_lbl.setWordWrap(True)
        self.value_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")

        layout.addWidget(lbl)
        layout.addWidget(self.value_lbl)

    def set_value(self, value: str, color: str | None = None) -> None:
        self.value_lbl.setText(value)
        if color:
            self.value_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")


class _EggsOptionButton(QFrame):
    """Card de ação clicável, no mesmo padrão visual dos cards de Restore."""

    clicked = Signal()

    def __init__(self, glyph: str, title: str, desc: str, color: str, parent=None, badge: str = "", action_label: str = ""):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("EggsOptionBtn")
        self.setFixedHeight(110)
        self.setStyleSheet(f"""
            QFrame#EggsOptionBtn {{
                background: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 10);
                border-radius: 18px;
            }}
            QFrame#EggsOptionBtn:hover {{
                background: rgba(255, 255, 255, 9);
                border: 1px solid {color};
            }}
            QFrame#EggsOptionBtn:disabled {{
                background: rgba(255, 255, 255, 2);
                border: 1px solid rgba(255, 255, 255, 6);
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignVCenter)

        ico_lbl = QLabel()
        ico_lbl.setFixedSize(48, 48)
        ico_lbl.setAlignment(Qt.AlignCenter)
        ico_lbl.setPixmap(qta.icon(glyph, color=color).pixmap(24, 24))
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
        self.title_lbl.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        self.title_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        title_row.addWidget(self.title_lbl)

        if badge:
            h = color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            badge_lbl = QLabel(badge.upper())
            badge_lbl.setFont(QFont("DejaVu Sans Mono", 8, QFont.Bold))
            badge_lbl.setStyleSheet(
                f"color: {color}; background: rgba({r},{g},{b},22); "
                f"border: 1px solid rgba({r},{g},{b},70); border-radius: 5px; "
                "padding: 2px 8px;"
            )
            title_row.addWidget(badge_lbl)

        title_row.addStretch()

        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setFont(QFont("DejaVu Sans Mono", 10))
        self.desc_lbl.setWordWrap(False)
        self.desc_lbl.setStyleSheet("color: #6b7a8d; background: transparent; border: none;")

        text.addLayout(title_row)
        text.addWidget(self.desc_lbl)
        layout.addWidget(ico_lbl, 0, Qt.AlignVCenter)
        layout.addLayout(text)
        layout.addStretch()

        self.action_btn = None
        if action_label:
            h = color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            self.action_btn = QPushButton(action_label)
            self.action_btn.setCursor(Qt.PointingHandCursor)
            self.action_btn.setFixedHeight(34)
            self.action_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba({r},{g},{b},18);
                    border: 1px solid rgba({r},{g},{b},110);
                    border-radius: 8px;
                    color: {color};
                    font-family: "DejaVu Sans Mono";
                    font-size: 10px;
                    font-weight: bold;
                    padding: 0 16px;
                }}
                QPushButton:hover {{
                    background: rgba({r},{g},{b},35);
                    border: 1px solid {color};
                }}
            """)
            # O botão dispara a mesma ação do card inteiro — clicar em
            # qualquer lugar do card ou só no botão tem o mesmo efeito.
            self.action_btn.clicked.connect(self.clicked.emit)
            layout.addWidget(self.action_btn, 0, Qt.AlignVCenter)

    def set_action_label(self, text: str) -> None:
        if self.action_btn is not None:
            self.action_btn.setText(text)

    def set_title(self, title: str) -> None:
        self.title_lbl.setText(title)

    def set_desc(self, desc: str) -> None:
        self.desc_lbl.setText(desc)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


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
            """
        )
        self._build_ui()

    def _build_ui(self) -> None:
        from ui.main_window import TopHeader  # import adiado — evita import circular

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(22)

        self.top_header = TopHeader()
        root.addWidget(self.top_header)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)

        btn_back = QPushButton("← Back to menu")
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

        subtitle = QLabel("Create, check and install Arch Linux live ISOs")
        subtitle.setFont(QFont("DejaVu Sans Mono", 10))
        subtitle.setStyleSheet("color: #9aa6b2;")

        h_layout.addLayout(title_row)
        h_layout.addWidget(subtitle)

        # ── Faixa de status ──────────────────────────────────────────────
        from core.eggs.eggs import get_dashboard_stats

        stats = get_dashboard_stats()

        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)

        self.stat_last_iso = _StatCard("ÚLTIMA ISO", stats["last_iso"] or "Nenhuma ISO gerada ainda")
        self.stat_ventoy = _VentoyCard()
        self.stat_ventoy.set_stats(
            stats["ventoy_free_gb"], stats["ventoy_total_gb"], stats["ventoy_fs_type"],
            free_pct=stats["ventoy_free_pct"],
        )

        # O card "Update Penguin's Eggs" já mostra a versão instalada e se
        # está atualizado — substitui o card de status separado que só
        # repetia essa mesma informação.
        install_title, install_desc, install_action = self._install_card_texts(
            stats["eggs_installed"], stats["eggs_version"], None
        )
        self.btn_install = _EggsOptionButton(
            glyph="mdi6.download-circle-outline",
            title=install_title,
            desc=install_desc,
            color="#ff9966",
            parent=self,
            badge="requer root",
            action_label=install_action,
        )
        self.btn_install.clicked.connect(self._on_install)

        stats_row.addWidget(self.stat_last_iso, 1)
        stats_row.addWidget(self.stat_ventoy, 1)
        stats_row.addWidget(self.btn_install, 1)

        # ── Cards de ação ────────────────────────────────────────────────
        cards = QGridLayout()
        cards.setSpacing(14)
        cards.setColumnStretch(0, 1)
        cards.setColumnStretch(1, 1)

        self.btn_create = _EggsOptionButton(
            glyph="mdi6.egg-easter",
            title="Create Penguin's Eggs",
            desc="Gera uma nova ISO live (ou move uma já pronta para o Ventoy).",
            color="#9bf0bd",
            parent=self,
            badge="requer root",
        )
        self.btn_create.clicked.connect(self._on_create)

        self.btn_check = _EggsOptionButton(
            glyph="mdi6.file-search-outline",
            title="Check Penguin's Eggs .iso",
            desc="Verifica se há uma .iso pendente e move/faz backup automaticamente.",
            color="#23a6ff",
            parent=self,
            badge="requer root",
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

        cards.addWidget(self.btn_create, 0, 0)
        cards.addWidget(self.btn_check, 0, 1)
        cards.addWidget(self.btn_broot, 1, 0)
        cards.addWidget(self.btn_nautilus, 1, 1)

        root.addWidget(header)
        root.addLayout(stats_row)
        root.addSpacing(14)
        root.addLayout(cards)
        root.addStretch(1)

        self._check_for_update()

    def _check_for_update(self) -> None:
        """Checa se há atualização do penguins-eggs disponível via AUR —
        roda numa QThread separada (faz chamada de rede, pode demorar
        alguns segundos) pra não travar a tela na abertura."""
        from PySide6.QtCore import QThread, Signal as QSignal
        from core.eggs.eggs import check_eggs_update

        class _UpdateCheckWorker(QThread):
            done = QSignal(object)

            def run(self):
                try:
                    self.done.emit(check_eggs_update())
                except Exception:
                    self.done.emit(None)

        self._update_check_worker = _UpdateCheckWorker(self)
        self._update_check_worker.done.connect(self._on_update_check_done)
        self._update_check_worker.start()

    def _on_update_check_done(self, update_version: str | None) -> None:
        self._last_update_version = update_version
        from core.eggs.eggs import get_dashboard_stats

        stats = get_dashboard_stats()
        install_title, install_desc, install_action = self._install_card_texts(
            stats["eggs_installed"], stats["eggs_version"], update_version
        )
        self.btn_install.set_title(install_title)
        self.btn_install.set_desc(install_desc)
        self.btn_install.set_action_label(install_action)

    def _install_card_texts(self, installed: bool, version: str | None, update_version: str | None) -> tuple[str, str, str]:
        """O card de instalação muda de texto sozinho conforme o
        penguins-eggs já estar instalado ou não, e mostra a versão atual
        e se há atualização disponível. Retorna (título, descrição, rótulo do botão)."""
        if not installed:
            return (
                "Penguin's Eggs and Calamares Install",
                "Instala o penguins-eggs e o módulo Calamares, se necessário.",
                "Instalar",
            )
        current = f"v{version}" if version else "versão instalada"
        if update_version:
            return (
                "Update Penguin's Eggs",
                f"Atual: {current} — nova versão v{update_version} disponível no AUR.",
                "Atualizar",
            )
        return (
            "Update Penguin's Eggs",
            f"Atual: {current} — já está na versão mais recente.",
            "Verificar",
        )

    def refresh_stats(self) -> None:
        from core.eggs.eggs import get_dashboard_stats

        stats = get_dashboard_stats()
        self.stat_last_iso.set_value(stats["last_iso"] or "Nenhuma ISO gerada ainda")
        self.stat_ventoy.set_stats(
            stats["ventoy_free_gb"], stats["ventoy_total_gb"], stats["ventoy_fs_type"],
            free_pct=stats["ventoy_free_pct"],
        )
        # Reaproveita o resultado da última checagem de update (feita em
        # background) — não faz outra chamada de rede a cada 8s do
        # auto-refresh, só nos momentos certos (abertura da tela, depois
        # de instalar/atualizar).
        update_version = getattr(self, "_last_update_version", None)
        install_title, install_desc, install_action = self._install_card_texts(
            stats["eggs_installed"], stats["eggs_version"], update_version
        )
        self.btn_install.set_title(install_title)
        self.btn_install.set_desc(install_desc)
        self.btn_install.set_action_label(install_action)

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
        self._check_for_update()

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
