from __future__ import annotations

import os
import shutil
import subprocess

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QPainter, QColor, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QPushButton, QScrollArea, QDialog, QPlainTextEdit,
)

from core.operation_manager import OperationManager
from core.clonezilla.manager import scan_clonezilla_backups, ClonezillaEntry
from core.workers.rclone_upload_worker import RcloneUploadWorker

# Upload pro Google Drive vai via rclone (remote "gdrive", configurado
# com `rclone config` — root_folder_id já aponta pra pasta CLONEZILLA
# real no Drive do Apollo, resolvida manualmente uma vez via
# Crypta > RAID 0 > RAID_BK > CLONEZILLA, já que "CLONEZILLA" na raiz
# do Drive é só um atalho que o gio/rclone não seguem sozinhos). O
# caminho <ano>/<mês> é relativo a essa raiz — ver RcloneUploadWorker.

TEXT = "#e4e7ec"
MUTED = "#8b92a3"
FAINT = "#6b7280"

ACCENT_BLUE = "#3b82f6"
ACCENT_BLUE_LIGHT = "#60a5fa"
ACCENT_GREEN = "#34d399"
ACCENT_AMBER = "#fbbf24"
ACCENT_RED = "#f87171"

FONT_FAMILY = "DejaVu Sans Mono"


def _rgba(hex_color: str, alpha: int) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"{r}, {g}, {b}, {alpha}"


def _fmt_size(size: int | None) -> str:
    if size is None:
        return "—"
    if size >= 1024 ** 3:
        return f"{size / 1024 ** 3:.1f} GB"
    if size >= 1024 ** 2:
        return f"{size / 1024 ** 2:.0f} MB"
    return f"{size} B"


class _StyledDialog(QDialog):
    """Diálogo modal no padrão visual do Carbonara — clonado de
    ExitConfirmDialog (main_window.py): frameless, WA_TranslucentBackground,
    overlay escuro pintado no paintEvent, card centralizado. Usado pra erro,
    confirmação e detalhe de erro em vez do QMessageBox padrão do sistema
    (que não segue o tema escuro do app)."""

    def __init__(
        self, parent, title: str, message: str, glyph: str, accent: str,
        detail: str = "", confirm_mode: bool = False, confirm_label: str = "Confirmar",
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignCenter)

        width = 460 if detail else 400
        self.card = QFrame(self)
        self.card.setObjectName("StyledDialogCard")
        self.card.setFixedWidth(width)
        self.card.setStyleSheet(f"""
            QFrame#StyledDialogCard {{
                background: #14151c;
                border: 1px solid rgba({_rgba(accent, 60)});
                border-radius: 18px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(0)

        icon_badge = QLabel()
        icon_badge.setFixedSize(44, 44)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setStyleSheet(f"background: rgba({_rgba(accent, 18)}); border-radius: 13px;")
        icon_badge.setPixmap(qta.icon(glyph, color=accent).pixmap(22, 22))
        card_layout.addWidget(icon_badge)
        card_layout.addSpacing(18)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont(FONT_FAMILY, 15, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT};")
        card_layout.addWidget(title_lbl)
        card_layout.addSpacing(8)

        msg_lbl = QLabel(message)
        msg_font = QFont(FONT_FAMILY, 10)
        msg_lbl.setFont(msg_font)
        msg_lbl.setStyleSheet(f"color: {MUTED};")
        msg_lbl.setWordWrap(True)
        # QLabel com wordWrap às vezes calcula um sizeHint baixo demais
        # antes da largura do layout se firmar, cortando/sobrepondo o
        # texto no título. Calcula a altura real necessária pra largura
        # conhecida do card e força isso explicitamente.
        available_width = width - 28 - 28  # descontando as margens do card
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QFontMetrics
        text_rect = QFontMetrics(msg_font).boundingRect(
            QRect(0, 0, available_width, 0), Qt.TextWordWrap, message,
        )
        msg_lbl.setFixedHeight(text_rect.height() + 8)
        card_layout.addWidget(msg_lbl)

        if detail:
            card_layout.addSpacing(14)
            detail_view = QPlainTextEdit()
            detail_view.setReadOnly(True)
            detail_view.setPlainText(detail)
            detail_view.setFixedHeight(140)
            detail_view.setStyleSheet(f"""
                QPlainTextEdit {{
                    background: rgba(255, 255, 255, 4);
                    border: 1px solid rgba(255, 255, 255, 10);
                    border-radius: 8px;
                    color: {TEXT};
                    font-family: "{FONT_FAMILY}";
                    font-size: 9px;
                    padding: 8px;
                }}
            """)
            card_layout.addWidget(detail_view)

        card_layout.addSpacing(22)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._confirmed = False

        if confirm_mode:
            btn_cancel = QPushButton("Cancelar")
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
                QPushButton:hover {{ background: rgba(255,255,255,14); }}
            """)
            btn_cancel.clicked.connect(self.reject)
            btn_row.addWidget(btn_cancel)

            btn_confirm = QPushButton(confirm_label)
            btn_confirm.setFixedHeight(40)
            btn_confirm.setStyleSheet(f"""
                QPushButton {{
                    background: {accent};
                    border: none;
                    border-radius: 10px;
                    color: #0a0b0f;
                    font-family: "{FONT_FAMILY}";
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: rgba({_rgba(accent, 210)}); }}
            """)
            btn_confirm.clicked.connect(self._on_confirm)
            btn_row.addWidget(btn_confirm)
        else:
            btn_close = QPushButton("Fechar")
            btn_close.setFixedHeight(40)
            btn_close.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,255,255,8);
                    border: 1px solid rgba(255,255,255,14);
                    border-radius: 10px;
                    color: {TEXT};
                    font-family: "{FONT_FAMILY}";
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: rgba(255,255,255,14); }}
            """)
            btn_close.clicked.connect(self.reject)
            btn_row.addWidget(btn_close)

        card_layout.addLayout(btn_row)
        outer.addWidget(self.card)
        outer.setAlignment(self.card, Qt.AlignCenter)

    def _on_confirm(self) -> None:
        self._confirmed = True
        self.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


def _show_error(title: str, message: str, parent=None, detail: str = "") -> None:
    dlg = _StyledDialog(parent, title, message, "mdi6.alert-circle-outline", ACCENT_RED, detail=detail)
    if parent is not None:
        dlg.setGeometry(parent.window().geometry())
    dlg.exec()


def _ask_confirm(
    parent, title: str, message: str, confirm_label: str = "Confirmar", danger: bool = False,
) -> bool:
    accent = ACCENT_RED if danger else ACCENT_BLUE_LIGHT
    glyph = "mdi6.trash-can-outline" if danger else "mdi6.help-circle-outline"
    dlg = _StyledDialog(
        parent, title, message, glyph, accent,
        confirm_mode=True, confirm_label=confirm_label,
    )
    if parent is not None:
        dlg.setGeometry(parent.window().geometry())
    dlg.exec()
    return dlg._confirmed


class _SectionCard(QFrame):
    """Mesmo padrão visual das seções ROOT/HOME do Timeshift: título
    colorido + subtítulo (caminho) + divisor sutil na cor de destaque."""

    def __init__(self, title_text: str, path_text: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { border: none; background: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 0, 0)
        head.setSpacing(10)

        labels = QVBoxLayout()
        labels.setSpacing(1)

        title = QLabel(title_text)
        title.setFont(QFont(FONT_FAMILY, 15, QFont.Bold))
        title.setStyleSheet(f"color: {accent_color};")

        path = QLabel(path_text)
        path.setFont(QFont(FONT_FAMILY, 8))
        path.setStyleSheet(f"color: {FAINT};")

        labels.addWidget(title)
        labels.addWidget(path)
        head.addLayout(labels)
        head.addStretch(1)

        divider = QFrame()
        divider.setFixedHeight(2)
        divider.setStyleSheet(f"background: rgba({_rgba(accent_color, 50)}); border: none;")

        self.body = QGridLayout()
        self.body.setSpacing(12)
        self.body.setContentsMargins(0, 0, 0, 0)
        self._card_count = 0

        root.addLayout(head)
        root.addWidget(divider)
        root.addSpacing(2)
        root.addLayout(self.body)

    def add_card(self, widget) -> None:
        row, col = divmod(self._card_count, 2)
        self.body.addWidget(widget, row, col)
        self._card_count += 1


class _EntryCard(QFrame):
    compress_requested = Signal(object)  # ClonezillaEntry
    delete_requested = Signal(object, bool)  # ClonezillaEntry, pending
    upload_requested = Signal(object)    # ClonezillaEntry

    def __init__(self, entry: ClonezillaEntry, pending: bool, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 4);
                border: 1px solid rgba(255, 255, 255, 10);
                border-radius: 10px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        icon_color = ACCENT_AMBER if pending else ACCENT_GREEN
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setPixmap(qta.icon("mdi6.disc", color=icon_color).pixmap(18, 18))
        icon_lbl.setStyleSheet(f"""
            QLabel {{
                background: rgba({_rgba(icon_color, 24)});
                border-radius: 9px;
            }}
        """)
        top_row.addWidget(icon_lbl)
        top_row.addStretch(1)

        badge_text = "PENDENTE" if pending else "COMPRIMIDO"
        badge = QLabel(f"  {badge_text}  ")
        badge.setFont(QFont(FONT_FAMILY, 8, QFont.Bold))
        badge.setStyleSheet(f"""
            QLabel {{
                background: rgba({_rgba(icon_color, 26)});
                color: {icon_color};
                border-radius: 8px;
                padding: 4px 2px;
                letter-spacing: 1px;
            }}
        """)
        top_row.addWidget(badge)
        root.addLayout(top_row)
        root.addSpacing(10)

        name_lbl = QLabel(entry.name)
        name_lbl.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
        name_lbl.setStyleSheet(f"color: {TEXT};")
        name_lbl.setWordWrap(True)
        root.addWidget(name_lbl)
        root.addSpacing(3)

        if pending:
            meta_text = f"{_fmt_size(entry.raw_size_bytes)}   ·   {entry.month_dir.name}"
        else:
            meta_text = f"{_fmt_size(entry.archive_size_bytes)}   ·   {entry.month_dir.name}"
        meta_lbl = QLabel(meta_text)
        meta_lbl.setFont(QFont(FONT_FAMILY, 9))
        meta_lbl.setStyleSheet(f"color: {MUTED};")
        root.addWidget(meta_lbl)
        root.addSpacing(12)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        if pending:
            self.btn_compress = QPushButton("Comprimir")
            self.btn_compress.setCursor(Qt.PointingHandCursor)
            self.btn_compress.setFixedHeight(34)
            self.btn_compress.setStyleSheet(f"""
                QPushButton {{
                    background: rgba({_rgba(ACCENT_BLUE, 30)});
                    border: 1px solid {ACCENT_BLUE_LIGHT};
                    border-radius: 8px;
                    color: {TEXT};
                    font-family: "{FONT_FAMILY}";
                    font-size: 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: rgba({_rgba(ACCENT_BLUE, 50)});
                }}
            """)
            self.btn_compress.clicked.connect(lambda: self.compress_requested.emit(entry))
            btn_row.addWidget(self.btn_compress, 1)
        else:
            self.btn_upload = QPushButton("Enviar")
            self.btn_upload.setCursor(Qt.PointingHandCursor)
            self.btn_upload.setFixedHeight(34)
            self.btn_upload.setStyleSheet(f"""
                QPushButton {{
                    background: rgba({_rgba(ACCENT_BLUE_LIGHT, 22)});
                    border: 1px solid rgba({_rgba(ACCENT_BLUE_LIGHT, 90)});
                    border-radius: 8px;
                    color: {ACCENT_BLUE_LIGHT};
                    font-family: "{FONT_FAMILY}";
                    font-size: 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: rgba({_rgba(ACCENT_BLUE_LIGHT, 40)});
                }}
            """)
            self.btn_upload.clicked.connect(lambda: self.upload_requested.emit(entry))
            btn_row.addWidget(self.btn_upload, 1)

            self.btn_delete = QPushButton("Excluir")
            self.btn_delete.setCursor(Qt.PointingHandCursor)
            self.btn_delete.setFixedHeight(34)
            self.btn_delete.setStyleSheet(f"""
                QPushButton {{
                    background: rgba({_rgba(ACCENT_RED, 18)});
                    border: 1px solid rgba({_rgba(ACCENT_RED, 90)});
                    border-radius: 8px;
                    color: {ACCENT_RED};
                    font-family: "{FONT_FAMILY}";
                    font-size: 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: rgba({_rgba(ACCENT_RED, 34)});
                }}
            """)
            self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(entry, pending))
            btn_row.addWidget(self.btn_delete, 1)

        root.addLayout(btn_row)


class ClonezillaPage(QWidget):
    """Gerenciador de backups Clonezilla — lista pastas cruas e arquivos
    .tar.zst já comprimidos em /mnt/MDSATA/CLONEZILLA, separados em duas
    seções (Pendentes / Já comprimidos), e permite disparar a compressão
    (tar+zstd, via pkexec) direto pela UI."""

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("QWidget { background: transparent; }")

        self._compress_proc: subprocess.Popen | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_compress_process)

        self._delete_proc: subprocess.Popen | None = None
        self._delete_poll_timer = QTimer(self)
        self._delete_poll_timer.setInterval(400)
        self._delete_poll_timer.timeout.connect(self._poll_delete_process)

        self._upload_dialog = None
        self._upload_worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(22)

        # ── Cabeçalho padrão do app (logo/specs/menu + Início) ─────────────
        from ui.main_window import AppHeaderBlock  # import adiado — evita import circular

        self.app_header = AppHeaderBlock(back_button=True)
        self.app_header.back_clicked.connect(self.back_requested.emit)
        root.addWidget(self.app_header)

        # ── Título da página ────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 14, 0, 0)
        header_row.setSpacing(14)

        icon_badge = QLabel()
        icon_badge.setFixedSize(48, 48)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setPixmap(qta.icon("mdi6.disc", color="#23a6ff").pixmap(26, 26))
        icon_badge.setStyleSheet("""
            QLabel {
                background: rgba(35, 166, 255, 34);
                border-radius: 10px;
            }
        """)
        header_row.addWidget(icon_badge)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(2)
        title_lbl = QLabel("Clonezilla Backups")
        title_lbl.setFont(QFont(FONT_FAMILY, 22, QFont.Bold))
        title_lbl.setStyleSheet("color: #23a6ff;")
        sub_lbl = QLabel("Compressão e gerenciamento das imagens do Clonezilla")
        sub_lbl.setFont(QFont(FONT_FAMILY, 10))
        sub_lbl.setStyleSheet(f"color: {MUTED};")
        title_block.addWidget(title_lbl)
        title_block.addWidget(sub_lbl)
        header_row.addLayout(title_block)

        header_row.addStretch(1)

        self.btn_refresh = QPushButton("↻  Atualizar")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setFixedHeight(38)
        self.btn_refresh.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 14);
                border-radius: 8px;
                color: {TEXT};
                font-family: "{FONT_FAMILY}";
                font-size: 10px;
                font-weight: bold;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 10);
            }}
        """)
        self.btn_refresh.clicked.connect(self.refresh_list)
        header_row.addWidget(self.btn_refresh)

        root.addLayout(header_row)

        # ── Lista de backups (scrollável) ──────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._list_host = QWidget()
        self._list_host.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(24)
        self._list_layout.addStretch(1)

        self.scroll.setWidget(self._list_host)
        root.addWidget(self.scroll, 1)

        self.empty_label = QLabel(
            "Nenhum backup encontrado em /mnt/MDSATA/CLONEZILLA.\n\n"
            "Gere um backup no Clonezilla primeiro — a pasta gerada por ele "
            "aparece aqui automaticamente assim que existir."
        )
        self.empty_label.setFont(QFont(FONT_FAMILY, 10))
        self.empty_label.setStyleSheet(f"color: {FAINT};")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.hide()
        root.addWidget(self.empty_label)

        self.refresh_list()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_list()

    def refresh_list(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        try:
            entries = scan_clonezilla_backups()
        except Exception as exc:
            _show_error("Clonezilla Backups", f"Erro ao listar backups: {exc}", parent=self)
            entries = []

        self.empty_label.setVisible(not entries)
        self.scroll.setVisible(bool(entries))

        pending = [e for e in entries if e.archive_path is None]
        compressed = [e for e in entries if e.archive_path is not None]

        if pending:
            section = _SectionCard(
                "PENDENTES", "Ainda não comprimidos — aguardando ação", ACCENT_AMBER,
            )
            for entry in pending:
                card = _EntryCard(entry, pending=True)
                card.compress_requested.connect(self._on_compress_requested)
                card.delete_requested.connect(self._on_delete_requested)
                section.add_card(card)
            self._list_layout.insertWidget(self._list_layout.count() - 1, section)

        if compressed:
            section = _SectionCard(
                "JÁ COMPRIMIDOS", "Arquivos .tar.zst prontos", ACCENT_GREEN,
            )
            for entry in compressed:
                card = _EntryCard(entry, pending=False)
                card.delete_requested.connect(self._on_delete_requested)
                card.upload_requested.connect(self._on_upload_requested)
                section.add_card(card)
            self._list_layout.insertWidget(self._list_layout.count() - 1, section)

    def _on_compress_requested(self, entry: ClonezillaEntry) -> None:
        if OperationManager.is_running():
            current = OperationManager.current()
            _show_error(
                "Carbonara", f"Outra operação exclusiva já está em andamento: {current}",
                parent=self,
            )
            return

        # Validação de espaço em disco: como o zstd às vezes comprime
        # pouco (imagens já compactadas pelo próprio Clonezilla — ex.
        # real observado: 66.2 GB → 63.1 GB), exige espaço livre pelo
        # menos igual ao tamanho da pasta original, de forma conservadora.
        if entry.raw_size_bytes:
            try:
                free_bytes = shutil.disk_usage(entry.month_dir).free
            except OSError as exc:
                _show_error(
                    "Carbonara Backup",
                    f"Não foi possível checar o espaço livre em {entry.month_dir}: {exc}",
                    parent=self,
                )
                return

            if free_bytes < entry.raw_size_bytes:
                needed_gb = entry.raw_size_bytes / 1024 ** 3
                free_gb = free_bytes / 1024 ** 3
                _show_error(
                    "Espaço insuficiente",
                    f"Não há espaço livre suficiente em {entry.month_dir} para "
                    f"comprimir '{entry.name}' com segurança.\n\n"
                    f"Necessário (estimado): {needed_gb:.1f} GB\n"
                    f"Disponível: {free_gb:.1f} GB\n\n"
                    f"Libere espaço no destino antes de tentar novamente.",
                    parent=self,
                )
                return

        estimate = ""
        if entry.raw_size_bytes:
            gb = entry.raw_size_bytes / 1024 ** 3
            estimate = f"\n\nTamanho: {gb:.1f} GB — pode levar bastante tempo (uso intenso de CPU)."

        if not _ask_confirm(
            self, "Comprimir backup",
            f"Comprimir '{entry.name}' em .tar.zst?{estimate}",
            confirm_label="Comprimir",
        ):
            return

        if not OperationManager.start("clonezilla", f"Comprimindo {entry.name}"):
            _show_error("Carbonara", "Outra operação exclusiva já está em andamento.", parent=self)
            return

        import json

        args_json = json.dumps({
            "name": entry.name,
            "month_dir": str(entry.month_dir),
        })

        cmd = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "clonezilla.compress",
            args_json,
        ]

        try:
            # stderr capturado (não streamado ao vivo — o progresso real
            # já aparece no BackupProgressDialog que roda dentro do
            # processo root) só pra dar um erro útil se algo falhar, em
            # vez de só o código de saída cru.
            self._compress_proc = subprocess.Popen(
                cmd, stderr=subprocess.PIPE, text=True,
            )
            self._poll_timer.start()
        except Exception as exc:
            OperationManager.finish()
            _show_error("Carbonara Backup", str(exc), parent=self)

    def _poll_compress_process(self) -> None:
        if self._compress_proc is None:
            return
        rc = self._compress_proc.poll()
        if rc is None:
            return

        self._poll_timer.stop()
        proc = self._compress_proc
        self._compress_proc = None
        OperationManager.finish()
        self.refresh_list()

        if rc not in (0, 126) and rc >= 0:
            stderr_text = ""
            try:
                if proc.stderr is not None:
                    stderr_text = proc.stderr.read().strip()
            except Exception:
                pass
            _show_error(
                "Carbonara Backup",
                f"Processo de compressão terminou com código {rc}.",
                parent=self,
                detail=stderr_text,
            )

    def _on_delete_requested(self, entry: ClonezillaEntry, pending: bool) -> None:
        if pending:
            target_path = entry.raw_path
            is_dir = True
            what = "a pasta original"
        else:
            target_path = entry.archive_path
            is_dir = False
            what = "o arquivo .tar.zst"

        if target_path is None:
            return

        if OperationManager.is_running():
            current = OperationManager.current()
            _show_error(
                "Carbonara", f"Outra operação exclusiva já está em andamento: {current}",
                parent=self,
            )
            return

        if not _ask_confirm(
            self, "Excluir backup",
            f"Excluir {what} de '{entry.name}'?\n\n{target_path}\n\n"
            f"Essa ação não pode ser desfeita.",
            confirm_label="Excluir",
            danger=True,
        ):
            return

        if not OperationManager.start("clonezilla", f"Excluindo {entry.name}"):
            _show_error("Carbonara", "Outra operação exclusiva já está em andamento.", parent=self)
            return

        import json

        args_json = json.dumps({"path": str(target_path), "is_dir": is_dir})

        cmd = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "clonezilla.delete",
            args_json,
        ]

        try:
            self._delete_proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
            self._delete_poll_timer.start()
        except Exception as exc:
            OperationManager.finish()
            _show_error("Carbonara Backup", str(exc), parent=self)

    def _poll_delete_process(self) -> None:
        if self._delete_proc is None:
            return
        rc = self._delete_proc.poll()
        if rc is None:
            return

        self._delete_poll_timer.stop()
        proc = self._delete_proc
        self._delete_proc = None
        OperationManager.finish()
        self.refresh_list()

        if rc not in (0, 126) and rc >= 0:
            stderr_text = ""
            try:
                if proc.stderr is not None:
                    stderr_text = proc.stderr.read().strip()
            except Exception:
                pass
            _show_error(
                "Carbonara Backup",
                f"Processo de exclusão terminou com código {rc}.",
                parent=self,
                detail=stderr_text,
            )

    def _on_upload_requested(self, entry: ClonezillaEntry) -> None:
        if entry.archive_path is None:
            return

        if OperationManager.is_running():
            current = OperationManager.current()
            _show_error(
                "Carbonara", f"Outra operação exclusiva já está em andamento: {current}",
                parent=self,
            )
            return

        # entry.month_dir é algo como /mnt/MDSATA/CLONEZILLA/2026/AUGUST —
        # usa o nome da pasta (mês) e da pasta pai (ano) como caminho
        # relativo dentro do remote rclone "gdrive" (cujo root_folder_id
        # já aponta pra pasta CLONEZILLA real no Drive), criando as
        # pastas automaticamente se ainda não existirem lá.
        month_name = entry.month_dir.name
        year_name = entry.month_dir.parent.name
        remote_folder = f"{year_name}/{month_name}"

        size_txt = f"\n\nTamanho: {_fmt_size(entry.archive_size_bytes)}" if entry.archive_size_bytes else ""
        if not _ask_confirm(
            self, "Enviar para o Google Drive",
            f"Enviar '{entry.archive_path.name}' para o Google Drive?{size_txt}\n\n"
            f"Destino: CLONEZILLA/{year_name}/{month_name}\n\n"
            f"Envia via rclone (remote 'gdrive').",
            confirm_label="Enviar",
        ):
            return

        if not OperationManager.start("clonezilla", f"Enviando {entry.name} para o Drive"):
            _show_error("Carbonara", "Outra operação exclusiva já está em andamento.", parent=self)
            return

        from ui.widgets.clonezilla_progress import ClonezillaProgressDialog

        dialog = ClonezillaProgressDialog(
            f"Enviando {entry.name}",
            icon_glyph="mdi6.cloud-upload-outline",
            body_title="Envio em andamento",
        )
        dialog.lbl_subtitle.setText(f"Enviando {entry.archive_path.name} para o Google Drive.")
        dialog.set_running(True)
        dialog.progress.setRange(0, 100)
        dialog.progress.setValue(0)
        dialog.set_status(f"Preparando envio de {entry.archive_path.name}...")
        dialog.set_current_file(entry.archive_path.name)
        dialog.append_log(f"=== UPLOAD {entry.archive_path.name} ===")
        dialog.append_log(f"Destino: CLONEZILLA/{year_name}/{month_name}")
        dialog.build_tree([entry.archive_path.name])

        worker = RcloneUploadWorker(entry.archive_path, remote_folder, parent=dialog)
        dialog.register_worker(worker)

        worker.progress_changed.connect(dialog.progress.setValue)
        worker.status_changed.connect(dialog.set_status)
        worker.log_line.connect(dialog.append_log)
        worker.detail_changed.connect(dialog.set_progress_detail)
        worker.bytes_changed.connect(dialog.set_bytes_progress)

        def _on_done() -> None:
            dialog.mark_file_done(entry.archive_path.name)
            dialog.set_status("Envio concluído.")
            dialog.set_current_file("—")
            dialog.progress.setValue(100)
            dialog.set_running(False)
            OperationManager.finish()

        def _on_failed(msg: str) -> None:
            dialog.append_log(f"ERRO: {msg}")
            dialog.set_status("Envio falhou.")
            dialog.set_running(False)
            OperationManager.finish()

        worker.finished_ok.connect(_on_done)
        worker.failed.connect(_on_failed)

        worker.start()
        dialog.exec()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.back_requested.emit()
            return
        super().keyPressEvent(event)
