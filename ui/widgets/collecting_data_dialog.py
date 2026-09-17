from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QProgressBar, QWidget

FONT_FAMILY = "DejaVu Sans Mono"


def _hex_to_rgb(hex_color: str) -> str:
    """'#3b82f6' -> '59, 130, 246' — usado pra montar rgba(...) no tema
    da página que chamou este diálogo."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r}, {g}, {b}"


class ModalBackdrop(QWidget):
    """Overlay semi-transparente cobrindo a janela principal por baixo
    do CollectingDataDialog — reforça visualmente que nada mais é
    clicável enquanto o carregamento roda (não só os botões desabilitados
    manualmente, como hoje o Eggs já faz em create/check). Filho da
    própria janela (não uma segunda janela top-level), pra acompanhar
    posição/tamanho/minimizar automaticamente sem código extra."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(6, 7, 10, 165);")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._sync_geometry()
        self.raise_()
        self.show()

    def _sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())

    def resizeToParent(self) -> None:
        self._sync_geometry()


class CollectingDataDialog(QDialog):
    """Dialog leve, genérico, exibido enquanto uma página carrega/atualiza
    dados em background — mesmo desenho do PairCheckProgressDialog
    (ui/widgets/backup_progress.py: header com ícone, spinner, status,
    barra indeterminada), extraído daqui pra ser reaproveitado por
    qualquer página (Timeshift, Eggs, Clonezilla, Doctor Arch, Disks...)
    em vez de cada uma ter sua própria cópia quase igual.

    Uso típico:
        dialog = CollectingDataDialog(
            title="Timeshift",
            status_text="Coletando snapshots...",
            subtitle_text="Destinos, tamanhos, últimas sincronizações...",
            icon_glyph="mdi6.history",
            accent_color="#23a6ff",
            parent=self.window(),
        )
        dialog.show()
        # ... dispara o worker/thread que carrega os dados ...
        # no callback de conclusão:
        dialog.accept()

    Sem botão de cancelar de propósito — é sempre um carregamento de
    leitura, rápido o bastante pra não precisar de saída no meio; ESC é
    ignorado, só o código que chamou fecha de verdade (accept/close)
    quando os dados terminam de chegar."""

    def __init__(
        self,
        title: str = "Carbonara",
        status_text: str = "Coletando dados...",
        subtitle_text: str = "",
        icon_glyph: str = "mdi6.progress-clock",
        accent_color: str = "#3b82f6",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(420, 160)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._accent = accent_color
        self._dots = 0
        self._spinner_frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self._build_ui(title, status_text, subtitle_text, icon_glyph)
        self._apply_styles()

        # Fundo escurecido cobrindo a janela principal por baixo deste
        # diálogo — reforça visualmente "nada mais é clicável agora",
        # não só os botões desabilitados manualmente (como o Eggs já
        # faz hoje em create/check). Só existe se um parent foi passado
        # (sem parent não tem o que escurecer).
        self._backdrop: ModalBackdrop | None = None
        if parent is not None:
            self._backdrop = ModalBackdrop(parent)
            parent.installEventFilter(self)

        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def eventFilter(self, watched, event) -> bool:
        if self._backdrop is not None and event.type() == event.Type.Resize:
            self._backdrop.resizeToParent()
        return super().eventFilter(watched, event)

    def _remove_backdrop(self) -> None:
        if self._backdrop is not None:
            parent = self.parent()
            if parent is not None:
                parent.removeEventFilter(self)
            self._backdrop.hide()
            self._backdrop.deleteLater()
            self._backdrop = None

    def _build_ui(self, title: str, status_text: str, subtitle_text: str, icon_glyph: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("CDHeader")
        header.setFixedHeight(46)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 18, 0)

        icon = QLabel()
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon(icon_glyph, color=self._accent).pixmap(16, 16))
        icon.setStyleSheet(
            f"QLabel {{ background: rgba({_hex_to_rgb(self._accent)}, 40); border-radius: 7px; }}"
        )

        lbl = QLabel(title)
        lbl.setFont(QFont(FONT_FAMILY, 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()

        body = QFrame()
        body.setObjectName("CDBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 16, 24, 20)
        b_layout.setSpacing(10)

        self.lbl_status = QLabel(status_text)
        self.lbl_status.setFont(QFont(FONT_FAMILY, 10))
        self.lbl_status.setStyleSheet("color: #c8d4e0;")
        self.lbl_status.setAlignment(Qt.AlignCenter)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        status_row.addStretch(1)

        self.lbl_spinner = QLabel("⠋")
        self.lbl_spinner.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        self.lbl_spinner.setStyleSheet(f"color: {self._accent};")
        status_row.addWidget(self.lbl_spinner)
        status_row.addWidget(self.lbl_status)
        status_row.addStretch(1)

        subtitle = QLabel(subtitle_text)
        subtitle.setFont(QFont(FONT_FAMILY, 9))
        subtitle.setStyleSheet("color: #6b7a8d;")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # modo indeterminado — pulsa
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setObjectName("CDBar")

        b_layout.addLayout(status_row)
        if subtitle_text:
            b_layout.addWidget(subtitle)
        b_layout.addSpacing(4)
        b_layout.addWidget(self.progress)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        rgb = _hex_to_rgb(self._accent)
        self.setStyleSheet(f"""
            CollectingDataDialog {{
                background: #131417;
                border-radius: 14px;
            }}
            QFrame#CDHeader {{
                background: rgba({rgb}, 35);
                border-bottom: 1px solid rgba({rgb}, 25);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
            QFrame#CDBody {{
                background: #131417;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }}
            QProgressBar#CDBar {{
                background: rgba({rgb}, 20);
                border: none;
                border-radius: 2px;
            }}
            QProgressBar#CDBar::chunk {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba({rgb}, 160),
                    stop:1 rgba({rgb}, 255)
                );
                border-radius: 2px;
            }}
        """)

    def set_status(self, text: str) -> None:
        """Deixa trocar a mensagem no meio (ex: 'Coletando snapshots...'
        -> 'Verificando integridade...') sem precisar recriar o diálogo."""
        self.lbl_status.setText(text)

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % len(self._spinner_frames)
        self.lbl_spinner.setText(self._spinner_frames[self._dots])

    def closeEvent(self, event) -> None:
        self._timer.stop()
        self._remove_backdrop()
        super().closeEvent(event)

    def accept(self) -> None:
        self._remove_backdrop()
        super().accept()

    def reject(self) -> None:
        # Sem botão de cancelar — é só leitura, rodando em background.
        # ESC não fecha nada; só o código externo fecha de verdade
        # (accept()/close()) quando o carregamento termina.
        pass

    def showEvent(self, event):
        """Centraliza na tela primária ao exibir."""
        super().showEvent(event)
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + (geo.height() - self.height()) // 2,
            )
