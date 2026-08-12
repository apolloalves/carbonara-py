from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QMouseEvent, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QPlainTextEdit, QPushButton, QFrame,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
)


class ClonezillaProgressDialog(QDialog):
    """Diálogo de progresso dedicado à compressão de backups Clonezilla —
    construído a partir do mockup original (elapsed timer, tempo estimado,
    progresso geral, operação atual, árvore "Transferring" com status por
    arquivo, e log). É um componente próprio, não uma versão modificada
    do BackupProgressDialog compartilhado — não afeta backup/sync/restore.

    API pública usada por core/clonezilla/manager.py:
      dialog.progress          QProgressBar (0-100)
      dialog.set_status(text)
      dialog.set_current_file(text)
      dialog.set_progress_detail(text)   — legenda "X GB de Y GB · Z MB/s"
      dialog.build_tree(paths)           — monta a árvore a partir da lista
                                            de caminhos relativos da pasta
      dialog.mark_file_done(path)        — marca um item da árvore como
                                            concluído (chamado conforme o
                                            tar -v relata cada arquivo)
      dialog.append_log(text)
      dialog.register_worker(worker)
      dialog.set_running(bool)
      dialog.btn_close
    """

    def __init__(self, title: str = "Comprimindo backup", icon_glyph: str = "mdi6.archive-arrow-down-outline", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._icon_glyph = icon_glyph
        self.setModal(True)
        self.setMinimumSize(980, 720)
        self.resize(1040, 780)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._workers: list = []
        self._cancel_countdown = 0
        self._cancel_timer = QTimer(self)
        self._cancel_timer.setInterval(1000)
        self._cancel_timer.timeout.connect(self._countdown_tick)

        self._had_failure = False
        self._timer_active = False
        self._elapsed_seconds = 0
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        self._log_buffer: list[str] = []
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(300)
        self._log_flush_timer.timeout.connect(self._flush_log_buffer)
        self._log_flush_timer.start()

        self._tree_items: dict[str, QTreeWidgetItem] = {}
        self._drag_pos = None

        self._build_ui()
        self._apply_styles()

        from PySide6.QtGui import QPalette, QColor as _QColor
        palette = self.log_view.palette()
        palette.setColor(QPalette.Base, _QColor(0, 0, 0, 50))
        self.log_view.setPalette(palette)

    def showEvent(self, event):
        super().showEvent(event)
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + (geo.height() - self.height()) // 2,
            )
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header customizado ───────────────────────────────────────────
        self.header = QFrame()
        self.header.setObjectName("DialogHeader")
        self.header.setFixedHeight(58)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 0, 16, 0)
        header_layout.setSpacing(0)

        lbl_icon = QLabel()
        lbl_icon.setFixedSize(38, 38)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setPixmap(qta.icon(self._icon_glyph, color="#9bf0bd").pixmap(22, 22))
        lbl_icon.setStyleSheet("QLabel { background: rgba(74, 222, 128, 40); border-radius: 10px; }")

        lbl_header = QLabel(self.windowTitle())
        lbl_header.setObjectName("HeaderTitle")
        lbl_header.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        self.lbl_header = lbl_header

        header_layout.addWidget(lbl_icon)
        header_layout.addSpacing(10)
        header_layout.addWidget(lbl_header)
        header_layout.addStretch(1)

        self.elapsed_badge = QFrame()
        self.elapsed_badge.setObjectName("ElapsedBadge")
        eb_layout = QHBoxLayout(self.elapsed_badge)
        eb_layout.setContentsMargins(10, 4, 12, 4)
        eb_layout.setSpacing(6)
        elapsed_icon = QLabel()
        elapsed_icon.setPixmap(qta.icon("mdi6.clock-outline", color="#9bf0bd").pixmap(14, 14))
        elapsed_icon.setStyleSheet("background: transparent;")
        self.lbl_elapsed = QLabel("00:00")
        self.lbl_elapsed.setObjectName("ElapsedTime")
        self.lbl_elapsed.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        eb_layout.addWidget(elapsed_icon)
        eb_layout.addWidget(self.lbl_elapsed)
        header_layout.addWidget(self.elapsed_badge)
        header_layout.addSpacing(12)

        self._btn_header_maximize = QPushButton()
        self._btn_header_maximize.setIcon(qta.icon("mdi6.window-maximize", color="#9aa6b2"))
        self._btn_header_maximize.setIconSize(QSize(15, 15))
        self._btn_header_maximize.setObjectName("HeaderMaximize")
        self._btn_header_maximize.setFixedSize(32, 32)
        self._btn_header_maximize.setToolTip("Maximizar")
        self._btn_header_maximize.clicked.connect(self._toggle_maximize)
        header_layout.addWidget(self._btn_header_maximize)
        header_layout.addSpacing(4)

        self._btn_header_close = QPushButton("✕")
        self._btn_header_close.setObjectName("HeaderClose")
        self._btn_header_close.setFixedSize(32, 32)
        self._btn_header_close.clicked.connect(self._on_header_close)
        header_layout.addWidget(self._btn_header_close)

        root.addWidget(self.header)

        # ── Corpo ────────────────────────────────────────────────────────
        body = QFrame()
        body.setObjectName("DialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 22, 24, 20)
        body_layout.setSpacing(0)

        self.lbl_title = QLabel(self.windowTitle())
        self.lbl_title.setObjectName("ProgressTitle")
        body_layout.addWidget(self.lbl_title)
        body_layout.addSpacing(3)

        self.lbl_subtitle = QLabel("Aguarde enquanto o Carbonara comprime o backup.")
        self.lbl_subtitle.setObjectName("ProgressSubtitle")
        body_layout.addWidget(self.lbl_subtitle)
        body_layout.addSpacing(14)

        # ── Card de status + elapsed/estimated ──────────────────────────
        info_card = QFrame()
        info_card.setObjectName("InfoCard")
        info_layout = QHBoxLayout(info_card)
        info_layout.setContentsMargins(18, 14, 18, 14)
        info_layout.setSpacing(14)

        info_icon = QLabel()
        info_icon.setFixedSize(44, 44)
        info_icon.setAlignment(Qt.AlignCenter)
        info_icon.setPixmap(qta.icon(self._icon_glyph, color="#9bf0bd").pixmap(22, 22))
        info_icon.setObjectName("InfoIcon")
        info_layout.addWidget(info_icon)

        self.lbl_status = QLabel("Aguardando início...")
        self.lbl_status.setObjectName("ProgressStatus")
        info_layout.addWidget(self.lbl_status)
        info_layout.addStretch(1)

        elapsed_col = QVBoxLayout()
        elapsed_col.setSpacing(1)
        elapsed_caption = QLabel("Tempo decorrido")
        elapsed_caption.setObjectName("TimeCaption")
        self.lbl_elapsed_big = QLabel("00:00")
        self.lbl_elapsed_big.setObjectName("TimeValue")
        elapsed_col.addWidget(elapsed_caption)
        elapsed_col.addWidget(self.lbl_elapsed_big)
        info_layout.addLayout(elapsed_col)

        sep = QFrame()
        sep.setObjectName("TimeSeparator")
        sep.setFixedWidth(1)
        info_layout.addWidget(sep)

        eta_col = QVBoxLayout()
        eta_col.setSpacing(1)
        eta_caption = QLabel("Tempo estimado restante")
        eta_caption.setObjectName("TimeCaption")
        self.lbl_eta = QLabel("—")
        self.lbl_eta.setObjectName("TimeValue")
        eta_col.addWidget(eta_caption)
        eta_col.addWidget(self.lbl_eta)
        info_layout.addLayout(eta_col)

        body_layout.addWidget(info_card)
        body_layout.addSpacing(14)

        # ── Progresso geral ──────────────────────────────────────────────
        overall_row = QHBoxLayout()
        lbl_overall = QLabel("Progresso geral")
        lbl_overall.setObjectName("SectionLabel")
        self.lbl_pct_big = QLabel("0%")
        self.lbl_pct_big.setObjectName("PctBig")
        overall_row.addWidget(lbl_overall)
        overall_row.addStretch(1)
        overall_row.addWidget(self.lbl_pct_big)
        body_layout.addLayout(overall_row)
        body_layout.addSpacing(6)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        self.progress.setObjectName("BackupProgress")
        self.progress.valueChanged.connect(self._on_progress_value_changed)
        body_layout.addWidget(self.progress)
        body_layout.addSpacing(6)

        self.lbl_progress_detail = QLabel("")
        self.lbl_progress_detail.setObjectName("ProgressDetail")
        body_layout.addWidget(self.lbl_progress_detail)
        body_layout.addSpacing(14)

        # ── Operação atual + árvore de transferência (lado a lado) ──────
        mid_row = QHBoxLayout()
        mid_row.setSpacing(14)

        current_box = QFrame()
        current_box.setObjectName("CurrentOpBox")
        cb_layout = QVBoxLayout(current_box)
        cb_layout.setContentsMargins(16, 12, 16, 12)
        cb_layout.setSpacing(6)
        lbl_current_heading = QLabel("Operação atual")
        lbl_current_heading.setObjectName("SectionLabel")
        cb_layout.addWidget(lbl_current_heading)
        self.lbl_current = _ElideLabel("Arquivo atual: —")
        self.lbl_current.setObjectName("ProgressCurrentFile")
        cb_layout.addWidget(self.lbl_current)
        cb_layout.addStretch(1)
        mid_row.addWidget(current_box, 1)

        tree_box = QFrame()
        tree_box.setObjectName("CurrentOpBox")
        tb_layout = QVBoxLayout(tree_box)
        tb_layout.setContentsMargins(16, 12, 16, 8)
        tb_layout.setSpacing(6)
        lbl_tree_heading = QLabel("Transferindo:")
        lbl_tree_heading.setObjectName("SectionLabel")
        tb_layout.addWidget(lbl_tree_heading)

        self.tree = QTreeWidget()
        self.tree.setObjectName("TransferTree")
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setFixedHeight(160)
        tb_layout.addWidget(self.tree)
        mid_row.addWidget(tree_box, 1)

        body_layout.addLayout(mid_row)
        body_layout.addSpacing(14)

        # ── Log ──────────────────────────────────────────────────────────
        lbl_log_heading = QLabel("Log")
        lbl_log_heading.setObjectName("SectionLabel")
        body_layout.addWidget(lbl_log_heading)
        body_layout.addSpacing(6)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("BackupLog")
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        body_layout.addWidget(self.log_view, stretch=1)
        body_layout.addSpacing(14)

        # ── Botões ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setMinimumWidth(160)
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        self.btn_close = QPushButton("Fechar")
        self.btn_close.setEnabled(False)
        self.btn_close.setFixedSize(110, 40)
        self.btn_close.setObjectName("BtnClose")
        self.btn_close.clicked.connect(self.accept)

        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_close)
        body_layout.addLayout(btn_row)

        root.addWidget(body, stretch=1)

    def _on_progress_value_changed(self, value: int) -> None:
        self.lbl_pct_big.setText(f"{value}%")
        if value <= 0 or not self._timer_active:
            self.lbl_eta.setText("—")
            return
        remaining_seconds = int(self._elapsed_seconds * (100 - value) / value)
        h, rem = divmod(remaining_seconds, 3600)
        m, s = divmod(rem, 60)
        self.lbl_eta.setText(f"{m:02d}:{s:02d}" if h == 0 else f"{h:02d}:{m:02d}:{s:02d}")

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            ClonezillaProgressDialog { background: #131417; border-radius: 14px; }

            QFrame#DialogHeader {
                background: rgba(74, 222, 128, 35);
                border-bottom: 1px solid rgba(74, 222, 128, 25);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QLabel#HeaderTitle { color: #ecf4ff; background: transparent; letter-spacing: 1px; }
            QPushButton#HeaderMaximize { background: transparent; border: none; border-radius: 6px; }
            QPushButton#HeaderMaximize:hover { background: rgba(35, 166, 255, 50); }
            QPushButton#HeaderClose { background: transparent; border: none; color: #9aa6b2; font-size: 15px; border-radius: 6px; }
            QPushButton#HeaderClose:hover { background: rgba(200, 60, 60, 60); color: #ff8888; }
            QFrame#ElapsedBadge { background: rgba(74, 222, 128, 22); border-radius: 8px; }
            QLabel#ElapsedTime { color: #9bf0bd; background: transparent; }

            QFrame#DialogBody { background: #131417; border-bottom-left-radius: 14px; border-bottom-right-radius: 14px; }

            QLabel#ProgressTitle { color: #ecf4ff; font-family: "DejaVu Sans Mono"; font-size: 19px; font-weight: 700; }
            QLabel#ProgressSubtitle { color: #9aa6b2; font-family: "DejaVu Sans Mono"; font-size: 11px; }

            QFrame#InfoCard { background: rgba(255,255,255,4); border: 1px solid rgba(255,255,255,12); border-radius: 12px; }
            QLabel#InfoIcon { background: rgba(74, 222, 128, 30); border-radius: 11px; }
            QLabel#ProgressStatus { color: #c8d4e0; font-family: "DejaVu Sans Mono"; font-size: 11px; }
            QLabel#TimeCaption { color: #6b7a8d; font-family: "DejaVu Sans Mono"; font-size: 9px; }
            QLabel#TimeValue { color: #9bf0bd; font-family: "DejaVu Sans Mono"; font-size: 16px; font-weight: 700; }
            QFrame#TimeSeparator { background: rgba(255,255,255,14); }

            QLabel#SectionLabel { color: #c8d4e0; font-family: "DejaVu Sans Mono"; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
            QLabel#PctBig { color: #9bf0bd; font-family: "DejaVu Sans Mono"; font-size: 15px; font-weight: 700; }
            QLabel#ProgressDetail { color: #6b7a8d; font-family: "DejaVu Sans Mono"; font-size: 10px; }

            QProgressBar#BackupProgress { background-color: rgba(255,255,255,8); border: none; border-radius: 5px; }
            QProgressBar#BackupProgress::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(35, 166, 80, 200), stop:1 rgba(94, 234, 149, 200));
                border-radius: 5px;
            }

            QFrame#CurrentOpBox { background: rgba(255,255,255,4); border: 1px solid rgba(255,255,255,12); border-radius: 12px; }
            QLabel#ProgressCurrentFile { color: #9aa6b2; font-family: "DejaVu Sans Mono"; font-size: 10px; font-style: italic; }

            QTreeWidget#TransferTree {
                background: transparent;
                border: none;
                color: #c8d4e0;
                font-family: "DejaVu Sans Mono";
                font-size: 10px;
                outline: none;
            }
            QTreeWidget#TransferTree::item { padding: 2px 0px; }

            QPlainTextEdit#BackupLog {
                border: 1px solid rgba(255,255,255,16);
                border-radius: 10px;
                color: #9aa6b2;
                font-family: "DejaVu Sans Mono";
                font-size: 12px;
                line-height: 180%;
                padding: 10px;
                selection-background-color: rgba(35, 166, 255, 80);
            }

            QPushButton#BtnCancel {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(200, 60, 60, 100);
                border-radius: 10px;
                color: #c8d4e0;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                padding: 8px 36px;
            }
            QPushButton#BtnCancel:hover { background: rgba(200, 60, 60, 40); border: 1px solid rgba(255, 100, 100, 180); color: #ffaaaa; }
            QPushButton#BtnCancel:disabled { color: #3a4a5a; border-color: rgba(200, 60, 60, 30); background: rgba(255,255,255,3); }

            QPushButton#BtnClose {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
            }
            QPushButton#BtnClose:hover { background: rgba(23, 147, 209, 70); border: 1px solid rgba(35, 166, 255, 180); }
            QPushButton#BtnClose:disabled { color: #3a4a5a; border-color: rgba(255,255,255,8); background: rgba(255,255,255,3); }
        """)

    # --------------------------------------------------- cancel countdown --

    def _on_cancel_clicked(self) -> None:
        if getattr(self, "_is_cancelling", False):
            return
        if self._cancel_countdown > 0:
            self._cancel_timer.stop()
            self._cancel_countdown = 0
            self._do_cancel()
            return
        self._cancel_countdown = 5
        self.btn_cancel.setText(f"Cancelar ({self._cancel_countdown}s)")
        self._cancel_timer.start()

    def _countdown_tick(self) -> None:
        self._cancel_countdown -= 1
        if self._cancel_countdown <= 0:
            self._cancel_timer.stop()
            self._cancel_countdown = 0
            self.btn_cancel.setText("Cancelar")
            self.set_status("Cancelamento ignorado. Operação continua...")
        else:
            self.btn_cancel.setText(f"Cancelar ({self._cancel_countdown}s) — clique p/ confirmar")

    def _do_cancel(self) -> None:
        self._is_cancelling = True
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("Cancelando...")
        self.set_status("Interrompendo compressão...")
        self.set_current_file("—")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(200, 60, 60, 40);
                border: 1px solid rgba(255, 100, 100, 180);
                border-radius: 10px;
                color: #ffaaaa;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                padding: 8px 36px;
            }
        """)
        self.btn_close.setEnabled(False)

        for worker in list(self._workers):
            worker.kill()
        for worker in list(self._workers):
            worker.wait(3000)
        self._workers.clear()

        self._cancel_safety_timer = QTimer(self)
        self._cancel_safety_timer.setSingleShot(True)
        self._cancel_safety_timer.setInterval(1500)
        self._cancel_safety_timer.timeout.connect(self._on_cancel_done)
        self._cancel_safety_timer.start()

    def _on_cancel_done(self) -> None:
        self.append_log("— Compressão cancelada. —")
        self.set_status("Cancelado.")
        self.set_running(False)
        self.btn_cancel.hide()
        self.btn_close.setEnabled(True)

    # ---------------------------------------------------- window drag -------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    def _on_header_close(self) -> None:
        if self.btn_close.isEnabled():
            self.accept()

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self._btn_header_maximize.setIcon(qta.icon("mdi6.window-maximize", color="#9aa6b2"))
            self._btn_header_maximize.setToolTip("Maximizar")
        else:
            self.showMaximized()
            self._btn_header_maximize.setIcon(qta.icon("mdi6.window-restore", color="#9aa6b2"))
            self._btn_header_maximize.setToolTip("Restaurar")

    def mouseDoubleClickEvent(self, event) -> None:
        if self.header.underMouse():
            self._toggle_maximize()
        super().mouseDoubleClickEvent(event)

    # ----------------------------------------------------------- public API --

    def register_worker(self, worker) -> None:
        self._workers.append(worker)
        worker.finished_ok.connect(lambda: self._cleanup_worker(worker))
        worker.failed.connect(lambda _: self._on_worker_failed(worker))

    def _on_worker_failed(self, worker) -> None:
        self._had_failure = True
        self._cleanup_worker(worker)

    def _cleanup_worker(self, worker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def append_log(self, text: str) -> None:
        self._log_buffer.append(text)

    def _flush_log_buffer(self) -> None:
        if not self._log_buffer:
            return
        from PySide6.QtGui import QTextCharFormat, QColor as _QColor, QTextCursor
        lines = self._log_buffer[:]
        self._log_buffer.clear()
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        for text in lines:
            if any(text.startswith(p) for p in ("ERRO:", "ERRO ", "✗")):
                color = "#ff8888"
            elif any(text.startswith(p) for p in ("✓", "--- ", "=== ")):
                color = "#9bf0bd"
            elif any(text.startswith(p) for p in ("AVISO:", "AVISO ")):
                color = "#ffb86b"
            elif text.startswith("$"):
                color = "#8fd4ff"
            else:
                color = "#9aa6b2"
            char_fmt = QTextCharFormat()
            char_fmt.setForeground(_QColor(color))
            cursor.insertText(("\n" if cursor.position() > 0 else "") + text, char_fmt)
        self.log_view.setTextCursor(cursor)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def set_current_file(self, text: str) -> None:
        self.lbl_current.set_text(f"Arquivo atual: {text}")

    def set_progress_detail(self, text: str) -> None:
        self.lbl_progress_detail.setText(text)

    def build_tree(self, relative_paths: list[str]) -> None:
        """Monta a árvore 'Transferindo:' a partir da lista de caminhos
        relativos (à pasta de origem) que serão lidos pelo tar — cada
        pasta intermediária vira um nó expansível, cada arquivo um item
        folha com um indicador de status (pendente/concluído)."""
        self.tree.clear()
        self._tree_items.clear()

        for rel_path in relative_paths:
            parts = rel_path.split("/")
            parent_item = None
            accumulated = ""
            for i, part in enumerate(parts):
                accumulated = f"{accumulated}/{part}" if accumulated else part
                if accumulated in self._tree_items:
                    parent_item = self._tree_items[accumulated]
                    continue
                is_leaf = i == len(parts) - 1
                item = QTreeWidgetItem([part])
                if is_leaf:
                    item.setIcon(0, qta.icon("mdi6.circle-outline", color="#4a5a6a"))
                else:
                    item.setIcon(0, qta.icon("mdi6.folder-outline", color="#8fd4ff"))
                if parent_item is None:
                    self.tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)
                self._tree_items[accumulated] = item
                parent_item = item

        self.tree.expandAll()

    def mark_file_done(self, relative_path: str) -> None:
        """Marca o item folha correspondente como concluído (chamado
        conforme o tar -v relata cada arquivo já escrito no archive)."""
        item = self._tree_items.get(relative_path)
        if item is not None:
            item.setIcon(0, qta.icon("mdi6.check-circle", color="#9bf0bd"))

    def _tick_elapsed(self) -> None:
        self._elapsed_seconds += 1
        h, rem = divmod(self._elapsed_seconds, 3600)
        m, s = divmod(rem, 60)
        text = f"{m:02d}:{s:02d}" if h == 0 else f"{h:02d}:{m:02d}:{s:02d}"
        self.lbl_elapsed.setText(text)
        self.lbl_elapsed_big.setText(text)
        self._on_progress_value_changed(self.progress.value())

    def set_running(self, running: bool) -> None:
        self.btn_cancel.setEnabled(running)
        self.btn_close.setEnabled(not running)
        if running and not self._timer_active:
            self._timer_active = True
            self._elapsed_timer.start()
        elif not running and self._timer_active:
            self._timer_active = False
            self._elapsed_timer.stop()

    def closeEvent(self, event) -> None:
        if not self.btn_close.isEnabled():
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if not self.btn_close.isEnabled():
            return
        super().reject()


class _ElideLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setText(text)

    def set_text(self, text: str) -> None:
        self._full_text = text
        self._update_elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elide()

    def _update_elide(self) -> None:
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(self._full_text, Qt.ElideMiddle, max(self.width(), 40))
        super().setText(elided)
