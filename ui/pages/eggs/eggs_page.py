from __future__ import annotations

import os
from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QPushButton,
    QMessageBox,
)


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

        btn_create = _EggsOptionButton(
            glyph="mdi6.egg-easter",
            title="Create Penguin's Eggs",
            desc="Gera uma nova ISO live (ou move uma já pronta para o Ventoy).",
            color="#9bf0bd",
            parent=self,
            badge="requer root",
        )
        btn_create.clicked.connect(self._on_create)

        btn_check = _EggsOptionButton(
            glyph="mdi6.file-search-outline",
            title="Check Penguin's Eggs .iso",
            desc="Verifica se há uma .iso pendente e move/faz backup automaticamente.",
            color="#23a6ff",
            parent=self,
            badge="requer root",
        )
        btn_check.clicked.connect(self._on_check)

        btn_broot = _EggsOptionButton(
            glyph="mdi6.folder-search-outline",
            title="Open files — broot",
            desc="Abre o diretório do Ventoy (destino final da ISO) no broot.",
            color="#c8a2ff",
            parent=self,
        )
        btn_broot.clicked.connect(lambda: self._open_files("broot"))

        btn_nautilus = _EggsOptionButton(
            glyph="mdi6.folder-open-outline",
            title="Open files — Nautilus",
            desc="Abre o diretório do Ventoy (destino final da ISO) no Nautilus.",
            color="#ffb86b",
            parent=self,
        )
        btn_nautilus.clicked.connect(lambda: self._open_files("nautilus"))

        btn_install = _EggsOptionButton(
            glyph="mdi6.download-circle-outline",
            title="Penguin's Eggs and Calamares Install",
            desc="Instala o penguins-eggs e o módulo Calamares, se necessário.",
            color="#ff9966",
            parent=self,
            badge="requer root",
        )
        btn_install.clicked.connect(self._on_install)

        cards.addWidget(btn_create, 0, 0)
        cards.addWidget(btn_check, 0, 1)
        cards.addWidget(btn_broot, 1, 0)
        cards.addWidget(btn_nautilus, 1, 1)
        cards.addWidget(btn_install, 2, 0)
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

    def _run_with_progress(self, func_name: str, dialog_title: str, preparing_text: str = "Aguardando...", icon_glyph: str = "mdi6.egg-outline") -> None:
        import subprocess
        from PySide6.QtCore import QThread, Signal as Sig

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
            python_bin,
            "-c",
            script,
        ]

        class _Runner(QThread):
            done = Sig(int, str)

            def __init__(self, cmd):
                super().__init__()
                self._cmd = cmd

            def run(self):
                result = subprocess.run(self._cmd, capture_output=True, text=True)
                self.done.emit(result.returncode, result.stderr or result.stdout)

        self._runner = _Runner(cmd)

        def on_done(returncode, output):
            self.refresh_stats()
            if returncode == 126 or "dismissed" in output.lower():
                return
            if returncode != 0:
                err = (output or f"exit code {returncode}").strip()
                QMessageBox.warning(self, "Penguin's Eggs", f"Erro ao executar:\n\n{err}")

        self._runner.done.connect(on_done)
        self._runner.start()

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
            QMessageBox.warning(self, "Penguin's Eggs", f"Não foi possível abrir: {exc}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.back_requested.emit()
            return
        super().keyPressEvent(event)
