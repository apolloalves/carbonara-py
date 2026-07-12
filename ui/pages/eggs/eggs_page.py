from __future__ import annotations

import os
from pathlib import Path

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

    def __init__(self, glyph: str, title: str, desc: str, color: str, parent=None, badge: str = ""):
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

        t = QLabel(title)
        t.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        t.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        title_row.addWidget(t)

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

        d = QLabel(desc)
        d.setFont(QFont("DejaVu Sans Mono", 10))
        d.setWordWrap(False)
        d.setStyleSheet("color: #6b7a8d; background: transparent; border: none;")

        text.addLayout(title_row)
        text.addWidget(d)
        layout.addWidget(ico_lbl, 0, Qt.AlignVCenter)
        layout.addLayout(text)
        layout.addStretch()

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

        self.stat_last_iso = _StatCard("ÚLTIMA ISO", stats["last_iso"] or "nenhuma gerada")
        self.stat_ventoy = _StatCard(
            "VENTOY",
            f"{stats['ventoy_free_gb']:.1f} GB livres" if stats["ventoy_free_gb"] is not None else "não montado",
            color="#9bf0bd" if stats["ventoy_free_gb"] is not None else "#6b7a8d",
        )
        self.stat_installed = _StatCard(
            "PENGUINS-EGGS",
            "instalado" if stats["eggs_installed"] else "não instalado",
            color="#9bf0bd" if stats["eggs_installed"] else "#ffb86b",
        )

        stats_row.addWidget(self.stat_last_iso, 1)
        stats_row.addWidget(self.stat_ventoy, 1)
        stats_row.addWidget(self.stat_installed, 1)

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

        self.btn_install = _EggsOptionButton(
            glyph="mdi6.download-circle-outline",
            title="Penguin's Eggs and Calamares Install",
            desc="Instala o penguins-eggs e o módulo Calamares, se necessário.",
            color="#ff9966",
            parent=self,
            badge="requer root",
        )
        self.btn_install.clicked.connect(self._on_install)

        cards.addWidget(self.btn_create, 0, 0)
        cards.addWidget(self.btn_check, 0, 1)
        cards.addWidget(self.btn_broot, 1, 0)
        cards.addWidget(self.btn_nautilus, 1, 1)
        cards.addWidget(self.btn_install, 2, 0)
        # (2, 1) fica livre — reservado para o próximo card que for adicionado aqui

        root.addWidget(header)
        root.addLayout(stats_row)
        root.addSpacing(14)
        root.addLayout(cards)
        root.addStretch(1)

    def refresh_stats(self) -> None:
        from core.eggs.eggs import get_dashboard_stats

        stats = get_dashboard_stats()
        self.stat_last_iso.set_value(stats["last_iso"] or "nenhuma gerada")
        self.stat_ventoy.set_value(
            f"{stats['ventoy_free_gb']:.1f} GB livres" if stats["ventoy_free_gb"] is not None else "não montado",
            color="#9bf0bd" if stats["ventoy_free_gb"] is not None else "#6b7a8d",
        )
        self.stat_installed.set_value(
            "instalado" if stats["eggs_installed"] else "não instalado",
            color="#9bf0bd" if stats["eggs_installed"] else "#ffb86b",
        )

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

        import subprocess

        project_root = Path(__file__).resolve().parents[3]
        python_bin = str(Path.home() / "venvs" / "pyside" / "bin" / "python3")

        script = f"""
import sys
sys.path.insert(0, {str(project_root)!r})

from PySide6.QtWidgets import QApplication
from core.eggs.eggs import {func_name}
from ui.widgets.eggs_progress import EggsProgressDialog

app = QApplication([])
dialog = EggsProgressDialog({dialog_title!r}, preparing_text={preparing_text!r}, icon_glyph={icon_glyph!r})
{func_name}(dialog)
dialog.exec()
"""
        cmd = [
            "pkexec",
            "env",
            f"DISPLAY={os.environ.get('DISPLAY', '')}",
            f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}",
            f"PYTHONPATH={project_root}",
            python_bin,
            "-c",
            script,
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
