from __future__ import annotations

import os
from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QTimer, QSize
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
    QComboBox,
    QListView,
    QScrollArea,
)


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


def style_combo_popup(combo: QComboBox) -> None:
    """Cópia exata do helper usado em snapshots_page.py (Timeshift) —
    estiliza o popup/lista suspensa do combo, mesmo tema azul."""
    view = combo.view()
    view.setMouseTracking(True)
    view.viewport().setMouseTracking(True)
    view.setAttribute(Qt.WA_Hover, True)
    view.viewport().setAttribute(Qt.WA_Hover, True)
    view.setUniformItemSizes(True)
    view.setStyleSheet(
        """
        QListView {
            background: #0a0f19;
            color: #ecf4ff;
            border: 1px solid rgba(31, 92, 255, 140);
            outline: 0;
            padding: 4px;
        }
        QListView::item {
            min-height: 32px;
            padding: 8px 10px;
            border-radius: 6px;
        }
        QListView::item:hover {
            background: rgba(35, 166, 255, 70);
            color: #ecf4ff;
        }
        QListView::item:selected {
            background: rgba(35, 166, 255, 180);
            color: #08111d;
        }
        QListView::item:selected:hover {
            background: rgba(70, 188, 255, 220);
            color: #08111d;
        }
        """
    )


def _parse_size_to_gb(size_str: str) -> float:
    """Converte strings human-readable do lsblk (ex: '65.7G', '512M',
    '1.2T') pra GB numérico, usado só pra ordenar por espaço livre."""
    if not size_str:
        return 0.0
    size_str = size_str.strip()
    try:
        unit = size_str[-1].upper()
        value = float(size_str[:-1])
    except (ValueError, IndexError):
        return 0.0
    multipliers = {"K": 1 / (1024 ** 2), "M": 1 / 1024, "G": 1, "T": 1024}
    return value * multipliers.get(unit, 1)


def _relevant_disks(disks: list) -> list:
    """Filtra discos irrelevantes (mesmo critério que o Timeshift usa em
    list_backup_destinations) e ordena por espaço livre — igual
    priorização do Timeshift, mais espaço primeiro."""
    IGNORED_PREFIXES = ("/run", "/boot", "/sys", "/proc", "/dev")
    IGNORED_FSTYPES = {"swap", "tmpfs", "devtmpfs", "squashfs", "overlay", "iso9660"}

    filtered = [
        d for d in disks
        if d.mountpoint
        and not d.mountpoint.startswith(IGNORED_PREFIXES)
        and d.fstype not in IGNORED_FSTYPES
    ]
    filtered.sort(key=lambda d: _parse_size_to_gb(d.avail), reverse=True)
    return filtered


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


class _DeleteIsoConfirmDialog(QDialog):
    """Dialog de confirmação estilizado pra remoção de ISO — mesmo padrão
    visual do _DeleteConfirmDialog em snapshots_page.py, substitui o
    QMessageBox.question() genérico que destoava do resto da UI."""

    def __init__(self, name: str, size_gb: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirmar exclusão")
        self.setModal(True)
        self.setFixedSize(480, 220)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(name, size_gb)
        self._apply_styles()

    def _build_ui(self, name: str, size_gb: float) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("DelHeader")
        header.setFixedHeight(48)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 16, 0)

        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.delete", color="#ff6666").pixmap(18, 18))
        icon.setStyleSheet("QLabel { background: rgba(200,60,60,40); border-radius: 8px; }")

        lbl = QLabel("Excluir ISO")
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        body = QFrame()
        body.setObjectName("DelBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 18, 24, 20)
        b_layout.setSpacing(10)

        warn = QLabel("Esta ação é irreversível. A ISO será permanentemente removida do disco.")
        warn.setWordWrap(True)
        warn.setFont(QFont("DejaVu Sans Mono", 9))
        warn.setStyleSheet("color: #c8d4e0;")

        iso_label = QLabel(f"{name}  •  {size_gb:.2f} GB")
        iso_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        iso_label.setStyleSheet(
            "color: #ff9966; background: rgba(200,60,60,20); "
            "border: 1px solid rgba(200,60,60,60); border-radius: 6px; padding: 4px 10px;"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("DelBtnCancel")
        btn_cancel.setFixedWidth(110)
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton("Excluir")
        btn_confirm.setObjectName("DelBtnConfirm")
        btn_confirm.setFixedWidth(110)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)

        b_layout.addWidget(warn)
        b_layout.addWidget(iso_label)
        b_layout.addStretch()
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QFrame#DelHeader {
                background: rgba(30, 10, 10, 255);
                border-bottom: 1px solid rgba(200, 60, 60, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#DelBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#DelBtnCancel {
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 8px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                padding: 6px 0;
            }
            QPushButton#DelBtnCancel:hover {
                background: rgba(23, 147, 209, 70);
                border-color: rgba(35, 166, 255, 180);
            }
            QPushButton#DelBtnConfirm {
                background: rgba(180, 40, 40, 180);
                border: 1px solid rgba(255, 80, 80, 160);
                border-radius: 8px;
                color: #ffffff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: 700;
                padding: 6px 0;
            }
            QPushButton#DelBtnConfirm:hover {
                background: rgba(220, 60, 60, 220);
                border-color: rgba(255, 120, 120, 220);
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


def _badge_style(color_hex: str, radius: int = 10) -> str:
    """Mesmo padrão de badge do _EggsOptionButton: fundo e borda na cor
    semântica do ícone, em vez do cinza quase invisível que os cards de
    stat (Ventoy/ISO) estavam usando antes."""
    h = color_hex.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (
        f"QLabel {{ background: rgba({r},{g},{b},40); "
        f"border-radius: {radius}px; border: 1px solid rgba({r},{g},{b},90); }}"
    )


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
        self.icon_lbl.setStyleSheet(_badge_style("#9bf0bd"))

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_lbl = QLabel("VENTOY")
        title_lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        title_lbl.setStyleSheet("color: #ecf4ff; background: transparent; border: none;")
        self.title_lbl = title_lbl

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
        label: str | None = None,
        mountpoint: str | None = None,
    ) -> None:
        if label is not None:
            self.title_lbl.setText(label)

        mount = mountpoint or "/mnt/VENTOY"

        if free_gb is None or total_gb is None or total_gb <= 0:
            self.detail_lbl.setText(f"não montado  •  {mount}")
            self.pct_lbl.setText("—")
            self.bar_fill.setGeometry(0, 0, 0, 5)
            return

        # Usa a porcentagem calculada pelo próprio `df` (idêntica ao que
        # `df -h` mostra no terminal) — só recalcula por conta própria se,
        # por algum motivo, ela não tiver vindo preenchida.
        pct_free = free_pct if free_pct is not None else (free_gb / total_gb) * 100
        fs = fs_type or "?"
        self.detail_lbl.setText(
            f"{free_gb:.1f} GB livres de {total_gb:.1f} GB  •  {mount}  •  {fs}"
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


class _IsoCard(QFrame):
    """Card da última ISO gerada, no mesmo estilo visual do _VentoyCard —
    ícone, título e linha de detalhe (sem barra de progresso, que não
    se aplica a um arquivo único)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("IsoCard")
        self.setStyleSheet("""
            QFrame#IsoCard {
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
        self.icon_lbl.setPixmap(qta.icon("mdi6.disc", color="#9bf0bd").pixmap(20, 20))
        self.icon_lbl.setStyleSheet(_badge_style("#9bf0bd"))

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_lbl = QLabel("ÚLTIMA ISO")
        title_lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        title_lbl.setStyleSheet("color: #ecf4ff; background: transparent; border: none;")

        self.name_lbl = QLabel("Nenhuma ISO gerada ainda")
        self.name_lbl.setFont(QFont("DejaVu Sans Mono", 9))
        self.name_lbl.setStyleSheet("color: #7d8a99; background: transparent; border: none;")
        self.name_lbl.setWordWrap(True)

        text_col.addWidget(title_lbl)
        text_col.addWidget(self.name_lbl)

        top_row.addWidget(self.icon_lbl)
        top_row.addLayout(text_col, 1)

        self.meta_lbl = QLabel("")
        self.meta_lbl.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        self.meta_lbl.setStyleSheet("color: #5eea95; background: transparent; border: none;")

        outer.addLayout(top_row)
        outer.addWidget(self.meta_lbl)

    def set_iso(self, name: str | None, date_str: str | None, size_gb: float | None) -> None:
        if not name:
            self.name_lbl.setText("Nenhuma ISO gerada ainda")
            self.meta_lbl.setText("")
            return
        self.name_lbl.setText(name)
        if date_str and size_gb is not None:
            self.meta_lbl.setText(f"{date_str}  •  {size_gb:.2f} GB")
        else:
            self.meta_lbl.setText("")


class _IsoListCard(QFrame):
    """Card de uma linha na listagem de ISOs existentes (item 3 do pedido
    do Apollo) — mesmo padrão visual do SnapshotCard em snapshots_page.py:
    ícone + nome + meta (data, tamanho, local) + botão de ação."""

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("IsoListCard")
        self.setStyleSheet("""
            QFrame#IsoListCard {
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 14px;
                background: rgba(255, 255, 255, 6);
            }
            QFrame#IsoListCard:hover {
                border: 1px solid rgba(255, 255, 255, 22);
                background: rgba(255, 255, 255, 9);
            }
            QPushButton {
                padding: 0px 18px;
                border-radius: 9px;
                border: 1px solid rgba(200, 60, 60, 100);
                background: rgba(255, 255, 255, 6);
                color: #c8d4e0;
                font: 700 9pt "DejaVu Sans Mono";
                min-height: 34px;
            }
            QPushButton:hover {
                background: rgba(200, 60, 60, 40);
                border: 1px solid rgba(255, 100, 100, 180);
                color: #ffaaaa;
            }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(16)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(38, 38)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setPixmap(qta.icon("mdi6.disc", color="#9bf0bd").pixmap(20, 20))
        icon_lbl.setStyleSheet(_badge_style("#9bf0bd"))

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        title = QLabel(entry.name)
        title.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        title.setStyleSheet("color: #ecf4ff;")

        meta = QLabel(f"{entry.date_str}  •  {entry.size_gb:.2f} GB  •  {entry.path.parent}")
        meta.setFont(QFont("DejaVu Sans Mono", 9))
        meta.setStyleSheet("color: #6b7a8d;")

        text_col.addWidget(title)
        text_col.addWidget(meta)

        self.btn_delete = QPushButton("DELETE")
        self.btn_delete.setIcon(qta.icon("mdi6.delete", color="#ff8888"))
        self.btn_delete.setIconSize(QSize(16, 16))

        root.addWidget(icon_lbl)
        root.addLayout(text_col, 1)
        root.addWidget(self.btn_delete)


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

        # ── Seletor de destino da ISO ────────────────────────────────────
        # Genérico: lista todos os discos/mounts disponíveis via
        # core/system/disks.py (list_disks), com o Ventoy pré-selecionado
        # por padrão (comportamento de sempre, agora escolhível).
        dest_row = QHBoxLayout()
        dest_row.setSpacing(10)

        dest_label = QLabel("Destino da ISO:")
        dest_label.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        dest_label.setStyleSheet("color: #9aa6b2;")

        self.cmb_iso_destination = QComboBox()
        self.cmb_iso_destination.setEditable(False)
        self.cmb_iso_destination.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_iso_destination.setMaxVisibleItems(8)
        self.cmb_iso_destination.setFocusPolicy(Qt.StrongFocus)
        self.cmb_iso_destination.setView(QListView())
        self.cmb_iso_destination.setMinimumWidth(420)
        self.cmb_iso_destination.setStyleSheet("""
            QComboBox {
                background: rgba(10, 15, 25, 230);
                color: #ecf4ff;
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 10px;
                padding: 8px 12px;
                min-height: 28px;
                font: 9pt "DejaVu Sans Mono";
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
                width: 0px;
                height: 0px;
            }
        """)

        # Chevron via qtawesome renderizado em PNG cacheado — mesmo truque
        # do Timeshift, já que o CSS de seta nativa do Qt não renderiza de
        # forma confiável.
        import tempfile as _tempfile
        chevron_path = Path(_tempfile.gettempdir()) / "carbonara_chevron_down_v2.png"
        if not chevron_path.exists():
            qta.icon("mdi6.chevron-down", color="#23a6ff").pixmap(28, 28).save(str(chevron_path))
        self.cmb_iso_destination.setStyleSheet(
            self.cmb_iso_destination.styleSheet()
            + "QComboBox::down-arrow { image: url(" + chevron_path.as_posix() + "); "
            + "width: 14px; height: 14px; margin-right: 10px; }"
        )

        style_combo_popup(self.cmb_iso_destination)


        dest_row.addWidget(dest_label)
        dest_row.addWidget(self.cmb_iso_destination, 1)

        self._refresh_destinations()
        self.cmb_iso_destination.currentIndexChanged.connect(self._on_destination_changed)

        # ── Faixa de status ──────────────────────────────────────────────
        from core.eggs.eggs import get_dashboard_stats

        stats = get_dashboard_stats()

        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)

        # stat_last_iso e stat_ventoy começam vazios aqui — refresh_stats(),
        # chamado no fim do _build_ui, já preenche os dois de acordo com o
        # disco selecionado no combo (que pode não ser o Ventoy).
        self.stat_last_iso = _IsoCard()
        self.stat_ventoy = _VentoyCard()

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
        root.addLayout(dest_row)
        root.addLayout(stats_row)
        root.addSpacing(14)
        root.addLayout(cards)
        root.addSpacing(18)

        # ── Listagem de ISOs existentes (estilo Timeshift, item 3) ───────
        iso_list_header = QLabel("ISOs existentes")
        iso_list_header.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        iso_list_header.setStyleSheet("color: #ecf4ff;")
        root.addWidget(iso_list_header)

        self.iso_scroll = QScrollArea()
        self.iso_scroll.setWidgetResizable(True)
        self.iso_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.iso_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.iso_scroll_content = QWidget()
        self.iso_scroll_layout = QVBoxLayout(self.iso_scroll_content)
        self.iso_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.iso_scroll_layout.setSpacing(10)
        self.iso_scroll_layout.addStretch(1)
        self.iso_scroll.setWidget(self.iso_scroll_content)

        root.addWidget(self.iso_scroll, 1)

        self.refresh_stats()
        self.rebuild_iso_list()

        self._check_for_update()

    def _refresh_destinations(self) -> None:
        """Popula o combo de destino com os discos/mounts disponíveis via
        core/system/disks.py — deixa o Ventoy pré-selecionado por padrão."""
        from core.system.disks import list_disks

        current_path = None
        if self.cmb_iso_destination.count() > 0:
            current_path = self.cmb_iso_destination.currentData()

        self.cmb_iso_destination.blockSignals(True)
        self.cmb_iso_destination.clear()

        disks = _relevant_disks(list_disks())
        ventoy_idx = 0
        for i, d in enumerate(disks):
            label = f"{d.mountpoint}  •  {d.model or d.name}  •  {d.avail} livre  •  {d.fstype}"
            self.cmb_iso_destination.addItem(label, d.mountpoint)
            if d.mountpoint == "/mnt/VENTOY":
                ventoy_idx = i

        self.cmb_iso_destination.blockSignals(False)

        if current_path:
            idx = self.cmb_iso_destination.findData(current_path)
            self.cmb_iso_destination.setCurrentIndex(idx if idx >= 0 else ventoy_idx)
        else:
            self.cmb_iso_destination.setCurrentIndex(ventoy_idx)

    def _on_destination_changed(self, index: int) -> None:
        if index < 0:
            return
        self.refresh_stats()

    def current_iso_destination(self) -> str:
        """Path do destino escolhido no combo — cai em /mnt/VENTOY se
        nada estiver selecionado (nenhum disco detectado, por exemplo)."""
        data = self.cmb_iso_destination.currentData()
        return data or "/mnt/VENTOY"

    def rebuild_iso_list(self) -> None:
        """Repopula a listagem de ISOs existentes — mesmo padrão de
        rebuild_snapshot_view em snapshots_page.py."""
        from core.eggs.eggs import list_existing_isos

        _clear_layout(self.iso_scroll_layout)

        entries = list_existing_isos()

        if not entries:
            empty = QLabel("Nenhuma ISO gerada ainda.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setFont(QFont("DejaVu Sans Mono", 9))
            empty.setStyleSheet("color: #6b7a8d; padding: 24px;")
            self.iso_scroll_layout.addWidget(empty)
            self.iso_scroll_layout.addStretch(1)
            return

        for entry in entries:
            card = _IsoListCard(entry)
            card.btn_delete.clicked.connect(lambda _, e=entry: self._delete_iso(e))
            self.iso_scroll_layout.addWidget(card)

        self.iso_scroll_layout.addStretch(1)

    def _delete_iso(self, entry) -> None:
        dialog = _DeleteIsoConfirmDialog(entry.name, entry.size_gb, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        import json
        import subprocess

        args_json = json.dumps({"path": str(entry.path)})
        cmd = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "eggs.delete_iso",
            args_json,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if result.returncode == 126:
                return  # usuário cancelou a autenticação
            err = result.stderr.strip() or f"exit code {result.returncode}"
            _show_error("Carbonara", f"Falha ao remover: {err}", parent=self)
            return
        self.rebuild_iso_list()

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
        from core.eggs.eggs import get_dashboard_stats, get_disk_stats, get_last_iso_for

        # eggs_installed/version não dependem do disco escolhido — segue
        # vindo do get_dashboard_stats geral.
        stats = get_dashboard_stats()

        # Destino + última ISO acompanham o disco selecionado no combo,
        # não mais o Ventoy fixo — a cada troca de seleção, os dois cards
        # se atualizam pra refletir aquele disco específico.
        dest_mount = self.current_iso_destination()
        dest_label = self._destination_label(dest_mount)

        disk_stats = get_disk_stats(dest_mount)
        self.stat_ventoy.set_stats(
            disk_stats["free_gb"], disk_stats["total_gb"], disk_stats["fs_type"],
            free_pct=disk_stats["free_pct"], label=dest_label, mountpoint=dest_mount,
        )

        last_iso = get_last_iso_for(dest_mount)
        self.stat_last_iso.set_iso(last_iso["name"], last_iso["date_str"], last_iso["size_gb"])

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

    def _destination_label(self, mountpoint: str) -> str:
        """Nome amigável do disco selecionado, pro título do card de
        destino — usa o nome do mountpoint em si (ex: 'VENTOY') como
        antes tinha hardcoded, mas agora vindo do combo."""
        name = mountpoint.rsplit("/", 1)[-1] or mountpoint
        return name.upper()

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

    def _run_with_progress(self, func_name: str, dialog_title: str, preparing_text: str = "Aguardando...", icon_glyph: str = "mdi6.egg-outline", extra_kwargs: dict | None = None) -> None:
        # Evita disparar uma segunda execução em paralelo se o usuário
        # clicar de novo enquanto o pkexec ainda está subindo.
        if self._proc is not None and self._proc.poll() is None:
            return

        import json
        import subprocess

        payload = {
            "func_name": func_name,
            "title": dialog_title,
            "preparing_text": preparing_text,
            "icon_glyph": icon_glyph,
        }
        if extra_kwargs:
            payload.update(extra_kwargs)
        args_json = json.dumps(payload)

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
        self.rebuild_iso_list()
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
        self.cmb_iso_destination.setEnabled(enabled)

    def _on_create(self) -> None:
        self._run_with_progress(
            "create_eggs", "Criando Penguin's Eggs...", "Criando ISO...", "mdi6.egg-easter",
            extra_kwargs={"destination": self.current_iso_destination()},
        )

    def _on_check(self) -> None:
        self._run_with_progress(
            "check_eggs", "Verificando Penguin's Eggs...", "Verificando .iso...", "mdi6.file-search-outline",
            extra_kwargs={"destination": self.current_iso_destination()},
        )

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
