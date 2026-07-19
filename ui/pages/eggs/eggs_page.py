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
    QLabel,
    QFrame,
    QPushButton,
    QDialog,
    QComboBox,
    QListView,
    QScrollArea,
    QSizePolicy,
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


from core.system.disks import list_relevant_disks


def _format_disk_label(d) -> str:
    """Mesma formatação usada no combo de destino — reusada também no
    card 'ÚLTIMA ISO' quando o disco selecionado não tem nenhuma ISO,
    pra mostrar a descrição completa do disco, não só o path."""
    return f"{d.mountpoint}  •  {d.model or d.name}  •  {d.avail} livre  •  {d.fstype}"


class _ElideLabel(QLabel):
    """QLabel que corta o texto com reticências no fim em vez de deixar
    o Qt cortar cru sem indicar que o texto continua. Usado no título dos
    cards de ação quando o card fica muito estreito (monitor pequeno)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text
        # Mínimo real (não 0): sem isso, se a linha ficar apertada e esse
        # for o único item "espremível" (badge tem tamanho fixo), o Qt
        # jogava 100% do aperto aqui, esmagando até sobrar só "..." —
        # aconteceu de verdade com o padding reduzido de um ajuste anterior.
        self.setMinimumWidth(60)

    def setText(self, text: str) -> None:
        self._full_text = text
        self._update_elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elide()

    def _update_elide(self) -> None:
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full_text, Qt.ElideRight, self.width())
        super().setText(elided)


class _ResponsiveCardGrid(QWidget):
    """Grid que reflui o número de colunas conforme a largura disponível
    — o Qt não tem nada nativo tipo CSS grid/flexbox com auto-fit, então
    isso recalcula manualmente a cada resize, igual uma media query faria
    na web. Os cards em si não mudam de tamanho, só a disposição.

    A cada reflow, o container INTEIRO (widget + layout) é destruído e
    recriado do zero — em vez de tentar limpar/reaproveitar o layout
    existente via takeAt(), que deixava estado órfão no Qt (o
    espaçamento vertical simplesmente sumia depois do primeiro reflow,
    mesmo com o valor certo no código)."""

    MIN_CARD_WIDTH = 400
    MAX_COLUMNS = 3
    ROW_SPACING = 28
    COL_SPACING = 14

    def __init__(self, cards: list, parent=None, min_card_width: int | None = None):
        super().__init__(parent)
        self._cards = cards
        self._current_columns = -1
        if min_card_width is not None:
            self.MIN_CARD_WIDTH = min_card_width
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._inner = None
        self._relayout(self.MAX_COLUMNS)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        columns = max(
            1,
            min(self.MAX_COLUMNS, (self.width() + self.COL_SPACING) // (self.MIN_CARD_WIDTH + self.COL_SPACING)),
        )
        if columns != self._current_columns:
            self._relayout(columns)

    def _relayout(self, columns: int) -> None:
        self._current_columns = columns

        # Destrói o container antigo por completo (widget + layout), em
        # vez de tentar limpar o layout existente item por item.
        if self._inner is not None:
            self._outer.removeWidget(self._inner)
            self._inner.setParent(None)
            self._inner.deleteLater()

        new_inner = QWidget()
        inner_vbox = QVBoxLayout(new_inner)
        inner_vbox.setContentsMargins(0, 0, 0, 0)
        inner_vbox.setSpacing(self.ROW_SPACING)

        for start in range(0, len(self._cards), columns):
            row_cards = self._cards[start:start + columns]
            row_layout = QHBoxLayout()
            row_layout.setSpacing(self.COL_SPACING)
            for card in row_cards:
                card.setParent(new_inner)
                row_layout.addWidget(card, 1)
            for _ in range(columns - len(row_cards)):
                row_layout.addStretch(1)
            inner_vbox.addLayout(row_layout)

        self._outer.addWidget(new_inner)
        self._inner = new_inner


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
        self.setFixedHeight(110)
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
        outer.setAlignment(Qt.AlignVCenter)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(48, 48)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setPixmap(qta.icon("mdi6.usb-flash-drive-outline", color="#9bf0bd").pixmap(24, 24))
        self.icon_lbl.setStyleSheet(_badge_style("#9bf0bd", radius=14))

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
        used_pct = 100 - pct_free
        fill_width = int(track_width * min(max(used_pct / 100, 0), 1))
        self.bar_fill.setGeometry(0, 0, fill_width, 5)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Recalcula a largura da barra preenchida proporcionalmente ao
        # redimensionar a tela.
        text = self.pct_lbl.text()
        if text != "—" and text.endswith("% livre"):
            try:
                pct_free = float(text.replace("% livre", ""))
                used_pct = 100 - pct_free
                fill_width = int(self.bar_track.width() * min(max(used_pct / 100, 0), 1))
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
        self.setFixedHeight(110)
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
        outer.setAlignment(Qt.AlignVCenter)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(48, 48)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setPixmap(qta.icon("mdi6.disc", color="#9bf0bd").pixmap(24, 24))
        self.icon_lbl.setStyleSheet(_badge_style("#9bf0bd", radius=14))

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel("ÚLTIMA ISO")
        title_lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        title_lbl.setStyleSheet("color: #ecf4ff; background: transparent; border: none;")
        self.title_lbl = title_lbl

        self.meta_lbl = QLabel("")
        self.meta_lbl.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        self.meta_lbl.setStyleSheet("color: #5eea95; background: transparent; border: none;")

        title_row.addWidget(title_lbl)
        title_row.addStretch(1)
        title_row.addWidget(self.meta_lbl)

        self.name_lbl = QLabel("Nenhuma ISO gerada ainda")
        self.name_lbl.setFont(QFont("DejaVu Sans Mono", 9))
        self.name_lbl.setStyleSheet("color: #7d8a99; background: transparent; border: none;")
        self.name_lbl.setWordWrap(True)

        text_col.addLayout(title_row)
        text_col.addWidget(self.name_lbl)

        top_row.addWidget(self.icon_lbl)
        top_row.addLayout(text_col, 1)

        outer.addLayout(top_row)

    def set_iso(
        self,
        name: str | None,
        date_str: str | None,
        size_gb: float | None,
        disk_label: str | None = None,
    ) -> None:
        if not name:
            self.title_lbl.setText("Sem ISO neste disco")
            self.name_lbl.setText(disk_label or "—")
            self.meta_lbl.setText("")
            return
        self.title_lbl.setText("ÚLTIMA ISO")
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
        icon_lbl.setFixedSize(48, 48)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setPixmap(qta.icon("mdi6.disc", color="#9bf0bd").pixmap(24, 24))
        icon_lbl.setStyleSheet(_badge_style("#9bf0bd", radius=14))

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

    def __init__(self, glyph: str, title: str, desc: str, color: str, parent=None, badge: str = "", action_label: str = "", compact: bool = False):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("EggsOptionBtn")
        # setMinimumHeight (não setFixedHeight): se a descrição quebrar em
        # mais linhas do que o previsto numa largura muito estreita, o
        # card cresce em vez de sobrepor/vazar texto pra fora da borda.
        self.setMinimumHeight(108 if compact else 128)
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
        layout.setContentsMargins(6, 0, 6, 0) if compact else layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6 if compact else 12)
        layout.setAlignment(Qt.AlignVCenter)

        icon_size = 32 if compact else 48
        pixmap_size = 16 if compact else 24
        ico_lbl = QLabel()
        ico_lbl.setFixedSize(icon_size, icon_size)
        ico_lbl.setAlignment(Qt.AlignCenter)
        ico_lbl.setPixmap(qta.icon(glyph, color=color).pixmap(pixmap_size, pixmap_size))
        h = color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        ico_lbl.setStyleSheet(
            f"QLabel {{ background: rgba({r},{g},{b},40); "
            f"border-radius: {10 if compact else 14}px; border: 1px solid rgba({r},{g},{b},90); }}"
        )

        text = QVBoxLayout()
        text.setSpacing(2 if compact else 1)
        text.setContentsMargins(0, 0, 0, 0)
        text.setAlignment(Qt.AlignVCenter)

        self.title_lbl = _ElideLabel(title)
        self.title_lbl.setFont(QFont("DejaVu Sans Mono", 10 if compact else 12, QFont.Bold))
        self.title_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")

        badge_lbl = None
        if badge:
            h = color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            lock_icon = qta.icon("mdi6.lock-outline", color=color).pixmap(18, 18)
            badge_lbl = QWidget()
            badge_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            badge_row_inner = QHBoxLayout(badge_lbl)
            badge_row_inner.setContentsMargins(6, 4, 6, 4)
            badge_icon_lbl = QLabel()
            badge_icon_lbl.setPixmap(lock_icon)
            badge_row_inner.addWidget(badge_icon_lbl)
            badge_lbl.setStyleSheet(
                f"background: rgba({r},{g},{b},22); "
                f"border: 1px solid rgba({r},{g},{b},70); border-radius: 5px;"
            )


        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setFont(QFont("DejaVu Sans Mono", 9 if compact else 10))
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setStyleSheet("color: #6b7a8d; background: transparent; border: none;")

        # Título sozinho na própria linha (largura toda disponível, sem
        # concorrência) — badge numa linha abaixo, dele, à esquerda. Título
        # e badge disputando a mesma linha nunca cabia direito em 3
        # colunas: ou o título cortava (sem stretch) ou o badge ficava
        # longe do texto (com stretch). Separar em linhas resolve de vez.
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self.title_lbl, 1)
        if badge_lbl is not None:
            title_row.addWidget(badge_lbl, 0, Qt.AlignTop)
        text.addLayout(title_row)
        text.addWidget(self.desc_lbl)
        layout.addWidget(ico_lbl, 0, Qt.AlignVCenter)
        layout.addLayout(text, 1)
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

        # Checagem de monitor separada, bem mais rápida (1s) — é uma
        # verificação leve (só geometria de janela, sem subprocess), então
        # não tem custo em rodar com frequência alta. Separado do refresh
        # de stats (8s) porque aquele chama df/pacman/etc., mais pesado.
        self._screen_check_timer = QTimer(self)
        self._screen_check_timer.setInterval(200)
        self._screen_check_timer.timeout.connect(self._check_screen_and_maybe_rebuild)

        # Garante que nenhum pkexec fique órfão rodando em segundo plano
        # se o app for fechado com uma operação (Create/Check/Install)
        # ainda em andamento.
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._terminate_pending_operation)

        # A largura mínima da página é decidida em _build_ui(), depois de
        # detectar o monitor atual (precisa ser menor no Dell 1280x1024).

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

    def _detect_compact_mode(self) -> bool:
        """Único ponto de detecção de monitor — usado tanto na construção
        inicial quanto na checagem periódica (_check_screen_and_maybe_rebuild).
        As duas chamadas PRECISAM usar exatamente o mesmo critério: usar
        critérios diferentes (cursor vs centro da janela) causava um loop
        infinito de reconstrução, já que os dois métodos podiam discordar
        pra sempre se o cursor estivesse num monitor diferente da janela.

        Prioriza o centro da janela (mais correto: "em qual monitor a
        janela está", não "onde está o mouse agora") — self.screen() fica
        de fora por já ter se mostrado não confiável nesse WM customizado
        (ficava preso no monitor errado mesmo depois de arrastar)."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        window = self.window()
        window_center = window.geometry().center() if window else None
        screen = (
            (QApplication.screenAt(window_center) if window_center is not None else None)
            or QApplication.screenAt(QCursor.pos())
            or QApplication.primaryScreen()
        )
        return bool(screen and screen.geometry().width() < 1400)

    def _build_ui(self) -> None:
        from ui.main_window import TopHeader  # import adiado — evita import circular

        self._compact_cards = self._detect_compact_mode()

        # Abaixo dessa largura, o cabeçalho/combo começam a sobrepor
        # conteúdo — no modo compacto (monitor menor), os elementos do
        # cabeçalho também ficam mais estreitos (ver mais abaixo), então
        # a largura mínima necessária cai bastante também.
        self.setMinimumWidth(820 if self._compact_cards else 1050)

        self._page_content = QWidget()
        root = QVBoxLayout(self._page_content)
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
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.egg-outline", color="#23a6ff").pixmap(26, 26))
        icon.setStyleSheet(_badge_style("#23a6ff", radius=14))

        title = QLabel("Penguin's Eggs")
        title.setFont(QFont("DejaVu Sans Mono", 22, QFont.Bold))
        title.setStyleSheet("color: #23a6ff;")

        subtitle = QLabel("Create, check and install Arch Linux live ISOs")
        self.subtitle_lbl = subtitle
        subtitle.setFont(QFont("DejaVu Sans Mono", 10))
        subtitle.setStyleSheet("color: #9aa6b2;")

        title_text_col = QVBoxLayout()
        title_text_col.setSpacing(2)
        title_text_col.addWidget(title)
        title_text_col.addWidget(subtitle)

        title_row.addWidget(icon)
        title_row.addLayout(title_text_col)
        title_row.setAlignment(icon, Qt.AlignVCenter)
        title_row.setAlignment(title_text_col, Qt.AlignVCenter)
        title_row.addStretch()

        # ÚLTIMA ISO é só informação (não é uma ação clicável) — sobe pro
        # topo da página, canto superior direito, junto do título, em vez
        # de ocupar espaço na grade de cards de ação.
        self.stat_last_iso = _IsoCard()
        self.stat_last_iso.setFixedWidth(360 if self._compact_cards else 520)
        title_row.addWidget(self.stat_last_iso)

        h_layout.addLayout(title_row)

        # ── Seletor de destino da ISO ────────────────────────────────────
        # Genérico: lista todos os discos/mounts disponíveis via
        # core/system/disks.py (list_disks), com o Ventoy pré-selecionado
        # por padrão (comportamento de sempre, agora escolhível).
        dest_row = QHBoxLayout()
        dest_row.setSpacing(20)

        dest_col = QVBoxLayout()
        dest_col.setSpacing(8)

        dest_label = QLabel("Destino da ISO:")
        dest_label.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        dest_label.setStyleSheet("color: #9aa6b2;")

        self.cmb_iso_destination = QComboBox()
        self.cmb_iso_destination.setEditable(False)
        self.cmb_iso_destination.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_iso_destination.setMaxVisibleItems(8)
        self.cmb_iso_destination.setFocusPolicy(Qt.StrongFocus)
        self.cmb_iso_destination.setView(QListView())
        self.cmb_iso_destination.setMinimumWidth(300 if self._compact_cards else 420)
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

        dest_col.addWidget(dest_label)
        dest_col.addWidget(self.cmb_iso_destination)
        dest_col.addStretch(1)

        self._refresh_destinations()
        self.cmb_iso_destination.currentIndexChanged.connect(self._on_destination_changed)

        # stat_ventoy começa vazio aqui — refresh_stats(), chamado no fim
        # do _build_ui, já preenche de acordo com o disco selecionado no
        # combo (que pode não ser o Ventoy).
        self.stat_ventoy = _VentoyCard()

        dest_row.addLayout(dest_col, 5)
        dest_row.addWidget(self.stat_ventoy, 4)

        # ── Faixa de status ──────────────────────────────────────────────
        from core.eggs.eggs import get_dashboard_stats

        stats = get_dashboard_stats()

        # O card "Update Penguin's Eggs" já mostra a versão instalada e se
        # está atualizado. Vai pro grid de 3 colunas junto com os demais,
        # em vez de ficar sozinho numa linha esticado a 100% da largura.
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
            compact=self._compact_cards,
        )
        self.btn_install.clicked.connect(self._on_install)

        # ── Cards de ação ────────────────────────────────────────────────
        self.btn_create = _EggsOptionButton(
            glyph="mdi6.egg-easter",
            title="Create Penguin's Eggs",
            desc="Gera uma ISO live (ou move a já pronta pro Ventoy).",
            color="#9bf0bd",
            parent=self,
            badge="requer root",
            compact=self._compact_cards,
        )
        self.btn_create.clicked.connect(self._on_create)

        self.btn_check = _EggsOptionButton(
            glyph="mdi6.file-search-outline",
            title="Check Penguin's Eggs .iso",
            desc="Verifica .iso pendente e faz backup automático.",
            color="#23a6ff",
            parent=self,
            badge="requer root",
            compact=self._compact_cards,
        )
        self.btn_check.clicked.connect(self._on_check)

        self.btn_broot = _EggsOptionButton(
            glyph="mdi6.folder-search-outline",
            title="Open files — broot",
            desc="Abre o Ventoy (destino da ISO) no broot.",
            color="#c8a2ff",
            parent=self,
            compact=self._compact_cards,
        )
        self.btn_broot.clicked.connect(lambda: self._open_files("broot"))

        self.btn_nautilus = _EggsOptionButton(
            glyph="mdi6.folder-open-outline",
            title="Open files — Nautilus",
            desc="Abre o Ventoy (destino da ISO) no Nautilus.",
            color="#ffb86b",
            parent=self,
            compact=self._compact_cards,
        )
        self.btn_nautilus.clicked.connect(lambda: self._open_files("nautilus"))

        # Reflui pra 2 ou 1 coluna conforme a largura disponível — não tem
        # equivalente nativo a media query no Qt, então isso recalcula
        # sozinho a cada resize (ver _ResponsiveCardGrid).
        cards = _ResponsiveCardGrid(
            [self.btn_create, self.btn_check, self.btn_install, self.btn_broot, self.btn_nautilus],
            min_card_width=260 if self._compact_cards else None,
        )

        root.addWidget(header)
        root.addLayout(dest_row)
        root.addSpacing(14)
        root.addWidget(cards)
        root.addSpacing(18)

        # ── Listagem de ISOs existentes (estilo Timeshift, item 3) ───────
        iso_list_header = QLabel("ISOs existentes")
        iso_list_header.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        iso_list_header.setStyleSheet("color: #ecf4ff;")
        root.addWidget(iso_list_header)

        iso_list_divider = QFrame()
        iso_list_divider.setFixedHeight(1)
        iso_list_divider.setStyleSheet("background: rgba(255, 255, 255, 14); border: none;")
        root.addWidget(iso_list_divider)

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

        # Envolve a página inteira num QScrollArea — sem isso, numa tela
        # de menor resolução (ex: Dell 1280x1024) ou com o grid refluindo
        # pra mais linhas, o conteúdo podia ficar mais alto que a janela
        # e simplesmente cortar o(s) último(s) card(s) sem nenhuma forma
        # de rolar até eles.
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.NoFrame)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        page_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        page_scroll.setWidget(self._page_content)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(page_scroll)

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

        disks = list_relevant_disks(list_disks())
        ventoy_idx = 0
        for i, d in enumerate(disks):
            label = _format_disk_label(d)
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

    def refresh_list(self) -> None:
        """Mesmo padrão do snapshots_page.py: um único ponto de entrada
        que releva o espaço livre de todos os discos (combo + cards) e
        reconstrói a listagem — chamado depois de qualquer delete,
        independente de qual disco foi afetado."""
        self._refresh_destinations()
        self.refresh_stats()
        self.rebuild_iso_list()

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
            self.refresh_list()
            return
        self.refresh_list()

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

    def _check_screen_and_maybe_rebuild(self) -> bool:
        """Retorna True se a UI foi reconstruída (monitor mudou de
        categoria compacto/normal), False se não precisou."""
        # Trava de reentrância: se por qualquer motivo _build_ui() já
        # estiver em andamento (ex: chamado a partir de si mesmo), nunca
        # mais entra em loop — só ignora essa checagem e tenta de novo no
        # próximo tick do timer (8s depois). Foi um loop assim (duas
        # detecções discordando pra sempre) que travou o app antes.
        if getattr(self, "_rebuilding_ui", False):
            return False

        now_compact = self._detect_compact_mode()

        if now_compact == getattr(self, "_compact_cards", now_compact):
            return False

        self._rebuilding_ui = True
        try:
            # Descarta o layout e todos os widgets filhos (idioma comum do
            # Qt pra limpar um layout: reatribui pra um widget descartável,
            # que leva tudo junto pro garbage collector) e reconstrói do
            # zero.
            old_layout = self.layout()
            if old_layout is not None:
                QWidget().setLayout(old_layout)
            self._build_ui()
        finally:
            self._rebuilding_ui = False
        return True

    def refresh_stats(self) -> None:
        from core.eggs.eggs import get_dashboard_stats, get_disk_stats, get_last_iso_for
        from core.system.disks import list_disks

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

        # Descrição completa do disco (mesma formatação do combo) —
        # usada pelo card "ÚLTIMA ISO" quando o disco selecionado não
        # tem nenhuma ISO salva.
        disk_info = next((d for d in list_disks() if d.mountpoint == dest_mount), None)
        dest_full_label = _format_disk_label(disk_info) if disk_info else dest_mount

        last_iso = get_last_iso_for(dest_mount)
        self.stat_last_iso.set_iso(
            last_iso["name"], last_iso["date_str"], last_iso["size_gb"], dest_full_label
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
        self._screen_check_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._stats_refresh_timer.stop()
        self._screen_check_timer.stop()
        super().hideEvent(event)
