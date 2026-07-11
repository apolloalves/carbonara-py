from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QPlainTextEdit, QPushButton, QFrame,
)


class BackupProgressDialog(QDialog):
    def __init__(self, title: str = "Carbonara Backup", preparing_text: str | None = None, icon_glyph: str = "mdi6.harddisk", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # Por padrão, o texto acima da barra de progresso reflete a própria
        # ação em curso (ex: "Criando Snapshot...", "Sincronizando
        # Snapshot..."), em vez de um "Preparando snapshot..." genérico que
        # fica factualmente errado assim que a cópia real começa.
        self._preparing_text = preparing_text if preparing_text is not None else f"{title}..."
        self._icon_glyph = icon_glyph
        self.setModal(True)
        self.setMinimumSize(900, 640)
        self.resize(960, 700)

        # Remove titlebar nativa — usamos header customizado
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

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

        # Buffer de log — evita travar a UI quando o rsync despeja muitas
        # linhas rapidamente (ex: milhares de arquivos pequenos de runtime
        # Flatpak). Sem isso, cada linha faz cursor+scrollbar update
        # síncrono, e uma rajada alta trava o event loop do Qt.
        self._log_buffer: list[str] = []
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(300)
        self._log_flush_timer.timeout.connect(self._flush_log_buffer)
        self._log_flush_timer.start()

        # Para drag da janela sem titlebar
        self._drag_pos = None

        self._build_ui()
        self._apply_styles()

        # Transparência do log — aplicada APÓS o stylesheet para não ser sobrescrita
        from PySide6.QtGui import QPalette, QColor
        palette = self.log_view.palette()
        palette.setColor(QPalette.Base, QColor(0, 0, 0, 50))
        self.log_view.setPalette(palette)

    def showEvent(self, event):
        """Centraliza na tela primária ao exibir — evita aparecer no monitor errado."""
        super().showEvent(event)
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + (geo.height() - self.height()) // 2,
            )

    # ------------------------------------------------------------------ UI --

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header customizado ───────────────────────────────────────────────
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
        lbl_icon.setStyleSheet(
            "QLabel { background: rgba(74, 222, 128, 40); border-radius: 10px; }"
        )

        lbl_header = QLabel(self.windowTitle())
        lbl_header.setObjectName("HeaderTitle")
        lbl_header.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        self.lbl_header = lbl_header

        header_layout.addWidget(lbl_icon)
        header_layout.addSpacing(10)
        header_layout.addWidget(lbl_header)
        header_layout.addStretch(1)

        # Badge de tempo decorrido — bem visível, no canto do header
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

        # Botão maximizar/restaurar — janela é frameless, então não tem
        # controle nativo do WM; alterna entre tamanho normal e maximizado.
        self._is_maximized = False
        self._normal_geometry = None
        self._btn_header_maximize = QPushButton()
        self._btn_header_maximize.setIcon(qta.icon("mdi6.window-maximize", color="#9aa6b2"))
        self._btn_header_maximize.setIconSize(QSize(15, 15))
        self._btn_header_maximize.setObjectName("HeaderMaximize")
        self._btn_header_maximize.setFixedSize(32, 32)
        self._btn_header_maximize.setToolTip("Maximizar")
        self._btn_header_maximize.clicked.connect(self._toggle_maximize)
        header_layout.addWidget(self._btn_header_maximize)
        header_layout.addSpacing(4)

        # Botão fechar no header (× apenas visual — só fecha se não estiver rodando)
        self._btn_header_close = QPushButton("✕")
        self._btn_header_close.setObjectName("HeaderClose")
        self._btn_header_close.setFixedSize(32, 32)
        self._btn_header_close.clicked.connect(self._on_header_close)
        header_layout.addWidget(self._btn_header_close)

        root.addWidget(self.header)

        # ── Corpo ────────────────────────────────────────────────────────────
        body = QFrame()
        body.setObjectName("DialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 26, 24, 20)
        body_layout.setSpacing(0)

        # Status principal
        self.lbl_title = QLabel(self._preparing_text)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setObjectName("ProgressTitle")
        body_layout.addWidget(self.lbl_title)
        body_layout.addSpacing(14)

        # Barra de progresso
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.setFixedHeight(22)
        self.progress.setObjectName("BackupProgress")
        body_layout.addWidget(self.progress)
        body_layout.addSpacing(10)

        # Linha de status (ex: "Copiando ROOT... 62%")
        self.lbl_status = QLabel("Aguardando início...")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setObjectName("ProgressStatus")
        body_layout.addWidget(self.lbl_status)
        body_layout.addSpacing(4)

        # Arquivo atual — elide para não expandir a janela
        self.lbl_current = _ElideLabel("Arquivo atual: —")
        self.lbl_current.setAlignment(Qt.AlignCenter)
        self.lbl_current.setObjectName("ProgressCurrentFile")
        body_layout.addWidget(self.lbl_current)
        body_layout.addSpacing(16)

        # Log
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("BackupLog")
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        body_layout.addWidget(self.log_view, stretch=1)
        body_layout.addSpacing(16)

        # Botões
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setMinimumWidth(130)
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

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            BackupProgressDialog {
                background: #131417;
                border-radius: 14px;
            }

            /* ── Header ── */
            QFrame#DialogHeader {
                background: rgba(74, 222, 128, 35);
                border-bottom: 1px solid rgba(74, 222, 128, 25);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }

            QLabel#HeaderIcon {
                color: rgba(35, 166, 255, 220);
                background: transparent;
            }

            QLabel#HeaderTitle {
                color: #ecf4ff;
                background: transparent;
                letter-spacing: 1px;
            }

            QPushButton#HeaderMaximize {
                background: transparent;
                border: none;
                border-radius: 6px;
            }
            QPushButton#HeaderMaximize:hover {
                background: rgba(35, 166, 255, 50);
            }

            QPushButton#HeaderClose {
                background: transparent;
                border: none;
                color: #9aa6b2;
                font-size: 15px;
                border-radius: 6px;
            }
            QPushButton#HeaderClose:hover {
                background: rgba(200, 60, 60, 60);
                color: #ff8888;
            }

            /* ── Body ── */
            QFrame#DialogBody {
                background: #131417;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }

            QLabel#ProgressTitle {
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 13px;
                font-weight: 700;
            }

            QLabel#ProgressStatus {
                color: #c8d4e0;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
            }

            QLabel#ProgressCurrentFile {
                color: #9aa6b2;
                font-family: "DejaVu Sans Mono";
                font-size: 10px;
                font-style: italic;
            }

            QFrame#ElapsedBadge {
                background: rgba(74, 222, 128, 22);
                border-radius: 8px;
            }

            QLabel#ElapsedTime {
                color: #9bf0bd;
                background: transparent;
            }

            QProgressBar#BackupProgress {
                background-color: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 4px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 10px;
                font-weight: 700;
                text-align: center;
            }
            QProgressBar#BackupProgress::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(35, 166, 80, 130),
                    stop:1 rgba(94, 234, 149, 130)
                );
                border-radius: 3px;
            }

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
            QPlainTextEdit#BackupLog QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 2px;
            }
            QPlainTextEdit#BackupLog QScrollBar::handle:vertical {
                background: rgba(255,255,255,30);
                border-radius: 5px;
                min-height: 24px;
            }
            QPlainTextEdit#BackupLog QScrollBar::handle:vertical:hover {
                background: rgba(74,222,128,90);
            }
            QPlainTextEdit#BackupLog QScrollBar::add-line:vertical,
            QPlainTextEdit#BackupLog QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QPlainTextEdit#BackupLog QScrollBar:horizontal {
                background: transparent;
                height: 10px;
                margin: 2px;
            }
            QPlainTextEdit#BackupLog QScrollBar::handle:horizontal {
                background: rgba(255,255,255,30);
                border-radius: 5px;
                min-width: 24px;
            }
            QPlainTextEdit#BackupLog QScrollBar::handle:horizontal:hover {
                background: rgba(74,222,128,90);
            }
            QPlainTextEdit#BackupLog QScrollBar::add-line:horizontal,
            QPlainTextEdit#BackupLog QScrollBar::sub-line:horizontal {
                width: 0px;
            }

            QPushButton#BtnCancel {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(200, 60, 60, 100);
                border-radius: 10px;
                color: #c8d4e0;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
            }
            QPushButton#BtnCancel:hover {
                background: rgba(200, 60, 60, 40);
                border: 1px solid rgba(255, 100, 100, 180);
                color: #ffaaaa;
            }
            QPushButton#BtnCancel:disabled {
                color: #3a4a5a;
                border-color: rgba(200, 60, 60, 30);
                background: rgba(255,255,255,3);
            }

            QPushButton#BtnClose {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
            }
            QPushButton#BtnClose:hover {
                background: rgba(23, 147, 209, 70);
                border: 1px solid rgba(35, 166, 255, 180);
            }
            QPushButton#BtnClose:disabled {
                color: #3a4a5a;
                border-color: rgba(255,255,255,8);
                background: rgba(255,255,255,3);
            }
        """)

    # --------------------------------------------------- cancel countdown --

    def _on_cancel_clicked(self) -> None:
        """Inicia contagem regressiva de 5s. Segunda clicada cancela imediatamente."""
        if self._cancel_countdown > 0:
            # segundo clique — cancela agora
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
            # Contagem zerou sem segundo clique → continua backup
            self.set_status("Cancelamento ignorado. Backup continua...")
        else:
            self.btn_cancel.setText(f"Cancelar ({self._cancel_countdown}s) — clique p/ confirmar")

    def _do_cancel(self) -> None:
        """Mata os processos rsync via PID e remove snapshots incompletos em background."""
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Cancelando...")
        self.set_status("Interrompendo backup...")
        self.set_current_file("—")

        # Animação de pontos enquanto limpa
        self._cancel_dots = 0
        self._cancel_anim = QTimer(self)
        self._cancel_anim.setInterval(400)
        self._cancel_anim.timeout.connect(self._cancel_anim_tick)
        self._cancel_anim.start()

        # Mata os processos rsync via SIGKILL — não bloqueia, não usa wait()
        for worker in list(self._workers):
            worker.kill()
        self._workers.clear()

        # Limpeza de disco em thread separada — rmtree pode demorar
        from PySide6.QtCore import QThread, Signal as QSignal

        class _CleanupThread(QThread):
            log_msg = QSignal(str)

            def __init__(self, dialog):
                super().__init__(dialog)
                self._dialog = dialog
                self._removed: list[str] = []

            def run(self):
                self._removed = self._dialog._cleanup_incomplete_snapshots()
                for path in self._removed:
                    self.log_msg.emit(f"Removido snapshot incompleto: {path}")

        self._cleanup_thread = _CleanupThread(self)
        self._cleanup_thread.log_msg.connect(self.append_log)
        self._cleanup_thread.finished.connect(self._on_cleanup_done)
        self._cleanup_thread.start()

    def _cancel_anim_tick(self) -> None:
        self._cancel_dots = (self._cancel_dots + 1) % 4
        dots = "." * self._cancel_dots
        self.btn_cancel.setText(f"Cancelando{dots}")

    def _on_cleanup_done(self) -> None:
        self._cancel_anim.stop()
        self.append_log("— Backup cancelado. Snapshot incompleto removido. —")
        # Fecha com código 2 → snapshots_page identifica cancelamento intencional
        self.done(2)

    def _cleanup_incomplete_snapshots(self) -> list[str]:
        """Remove snapshots com status 'running' ou 'failed'. Retorna paths removidos."""
        import json
        import shutil
        from pathlib import Path

        removed = []
        for base in (Path("/mnt"), Path("/media")):
            if not base.exists():
                continue
            for snap_json in base.rglob("snapshot.json"):
                try:
                    data = json.loads(snap_json.read_text(encoding="utf-8"))
                    if data.get("status") in ("running", "failed"):
                        target = snap_json.parent
                        shutil.rmtree(target, ignore_errors=True)
                        removed.append(str(target))
                except Exception:
                    continue
        return removed

    # ---------------------------------------------------- window drag -------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    def _on_header_close(self) -> None:
        if any(w.isRunning() for w in self._workers):
            self.set_status("Backup em execução. Use Cancelar para interromper.")
            return
        self.accept()

    def _toggle_maximize(self) -> None:
        """Janela frameless não tem controle nativo de maximizar do WM —
        alterna manualmente entre o tamanho normal e a área disponível
        da tela (guardando geometria original para poder restaurar)."""
        if not self._is_maximized:
            self._normal_geometry = self.geometry()
            from PySide6.QtWidgets import QApplication
            screen = self.screen() or QApplication.primaryScreen()
            if screen:
                self.setGeometry(screen.availableGeometry())
            self._btn_header_maximize.setIcon(qta.icon("mdi6.window-restore", color="#9aa6b2"))
            self._btn_header_maximize.setToolTip("Restaurar")
            self._is_maximized = True
        else:
            if self._normal_geometry is not None:
                self.setGeometry(self._normal_geometry)
            self._btn_header_maximize.setIcon(qta.icon("mdi6.window-maximize", color="#9aa6b2"))
            self._btn_header_maximize.setToolTip("Maximizar")
            self._is_maximized = False

    def mouseDoubleClickEvent(self, event) -> None:
        """Duplo clique no header também alterna maximizar, como em janelas normais."""
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
        """Enfileira a linha no buffer — o flush acontece a cada 300ms via QTimer."""
        self._log_buffer.append(text)

    def _flush_log_buffer(self) -> None:
        """Descarrega o buffer no QPlainTextEdit de uma vez — chamado pelo QTimer."""
        if not self._log_buffer:
            return

        from PySide6.QtGui import QTextCharFormat, QColor, QTextCursor

        lines = self._log_buffer[:]
        self._log_buffer.clear()

        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)

        for text in lines:
            # Paleta por tipo de linha
            if any(text.startswith(p) for p in ("ERRO:", "ERRO ", "✗")):
                color = "#ff8888"
            elif any(text.startswith(p) for p in ("✓", "--- ", "=== ")):
                color = "#9bf0bd"
            elif any(text.startswith(p) for p in ("AVISO:", "AVISO ", "  ✗")):
                color = "#ffb86b"
            elif text.startswith("$"):
                color = "#8fd4ff"
            elif text.startswith("Copiando:"):
                color = "#c8d4e0"       # branco suave — legível mas não dominante
            elif text.startswith("Tempo decorrido:"):
                color = "#6b7a8d"
            elif not text.strip():
                color = "#000000"
            else:
                color = "#9aa6b2"

            char_fmt = QTextCharFormat()
            char_fmt.setForeground(QColor(color))
            cursor.insertText(("\n" if cursor.position() > 0 else "") + text, char_fmt)

        self.log_view.setTextCursor(cursor)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def set_current_file(self, text: str) -> None:
        self.lbl_current.set_text(f"Arquivo atual: {text}")

    def _tick_elapsed(self) -> None:
        self._elapsed_seconds += 1
        h, rem = divmod(self._elapsed_seconds, 3600)
        m, s = divmod(rem, 60)
        text = f"{m:02d}:{s:02d}" if h == 0 else f"{h:02d}:{m:02d}:{s:02d}"
        self.lbl_elapsed.setText(text)

    def set_running(self, running: bool) -> None:
        self.btn_cancel.setEnabled(running)
        self.btn_close.setEnabled(not running)

        if running and not self._timer_active:
            self._timer_active = True
            self._elapsed_seconds = 0
            self.lbl_elapsed.setText("00:00")
            self._elapsed_timer.start()
        elif not running and self._timer_active:
            self._timer_active = False
            self._elapsed_timer.stop()
            self._show_result_inline()

    def _show_result_inline(self) -> None:
        """Exibe o resultado (sucesso ou falha) diretamente no dialog, sem abrir nova janela."""
        elapsed = self.lbl_elapsed.text()
        status = self.lbl_status.text() or ("Operação concluída com sucesso." if not self._had_failure else "Operação concluída com erros.")

        self.append_log("")
        if self._had_failure:
            self.lbl_status.setStyleSheet("color: #ff8888; font-weight: bold;")
            self.append_log(f"ERRO: {status}")
            self.append_log(f"Tempo decorrido: {elapsed}")
        else:
            self.lbl_status.setStyleSheet("color: #9bf0bd; font-weight: bold;")
            self.append_log(f"✓ {status}")
            self.append_log(f"Tempo decorrido: {elapsed}")

        # Garante que as últimas linhas apareçam na hora, sem esperar o
        # próximo tick do timer de 300ms (a operação já terminou).
        self._flush_log_buffer()

    def closeEvent(self, event) -> None:
        if any(w.isRunning() for w in self._workers):
            event.ignore()
            self.set_status("Backup em execução. Use Cancelar para interromper.")
            return
        super().closeEvent(event)


# ── Dialog de sucesso ────────────────────────────────────────────────────────

class _SuccessDialog(QDialog):
    """Dialog exibido ao concluir uma operação de backup/sync com sucesso."""

    def __init__(self, message: str, elapsed_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Concluído")
        self.setModal(True)
        self.setFixedSize(440, 220)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(message, elapsed_text)
        self._apply_styles()

    def _build_ui(self, message: str, elapsed_text: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("SuccessHeader")
        header.setFixedHeight(56)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 18, 0)

        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.check-circle", color="#9bf0bd").pixmap(22, 22))
        icon.setStyleSheet(
            "QLabel { background: rgba(74,222,128,40); border-radius: 9px; }"
        )

        lbl_title = QLabel("Concluído com sucesso")
        lbl_title.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl_title.setStyleSheet("color: #ffffff; background: transparent;")

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl_title)
        h_layout.addStretch()

        body = QFrame()
        body.setObjectName("SuccessBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 22, 28, 22)
        b_layout.setSpacing(10)

        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setFont(QFont("DejaVu Sans Mono", 10))
        lbl_msg.setStyleSheet("color: #c8d4e0;")

        b_layout.addWidget(lbl_msg)

        if elapsed_text:
            lbl_elapsed = QLabel(elapsed_text)
            lbl_elapsed.setFont(QFont("DejaVu Sans Mono", 9))
            lbl_elapsed.setStyleSheet("color: #6b7a8d;")
            b_layout.addWidget(lbl_elapsed)

        b_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("SuccessBtnOk")
        btn_ok.setFixedSize(100, 38)
        btn_ok.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#SuccessHeader {
                background: rgba(74, 222, 128, 35);
                border-bottom: 1px solid rgba(74, 222, 128, 25);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QFrame#SuccessBody {
                background: #131417;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QPushButton#SuccessBtnOk {
                background: rgba(74, 222, 128, 180);
                border: 1px solid rgba(74, 222, 128, 220);
                border-radius: 10px;
                color: #08111d;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#SuccessBtnOk:hover {
                background: rgba(94, 234, 149, 220);
            }
        """)


# ── Dialog de checagem do snapshot irmão ────────────────────────────────────

class PairCheckProgressDialog(QDialog):
    """Dialog leve exibido enquanto verificamos, via rsync --dry-run, se o
    snapshot irmão (ROOT/HOME) tem mudanças pendentes reais. Visual baseado
    no dialog de progresso de exclusão de snapshot, com tema verde de sync."""

    def __init__(self, sibling_label: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Verificando snapshot irmão")
        self.setModal(True)
        self.setFixedSize(420, 160)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._dots = 0
        self._build_ui(sibling_label)
        self._apply_styles()

        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _build_ui(self, sibling_label: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("PCHeader")
        header.setFixedHeight(46)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 18, 0)

        icon = QLabel()
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.sync", color="#9bf0bd").pixmap(16, 16))
        icon.setStyleSheet(
            "QLabel { background: rgba(74,222,128,40); border-radius: 7px; }"
        )

        lbl = QLabel("Verificando Snapshot Irmão")
        lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()

        body = QFrame()
        body.setObjectName("PCBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 16, 24, 20)
        b_layout.setSpacing(10)

        self.lbl_status = QLabel("Verificando alterações pendentes...")
        self.lbl_status.setFont(QFont("DejaVu Sans Mono", 10))
        self.lbl_status.setStyleSheet("color: #c8d4e0;")
        self.lbl_status.setAlignment(Qt.AlignCenter)

        snap_lbl = QLabel(sibling_label)
        snap_lbl.setFont(QFont("DejaVu Sans Mono", 9))
        snap_lbl.setStyleSheet("color: #6b7a8d;")
        snap_lbl.setAlignment(Qt.AlignCenter)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # modo indeterminado — pulsa
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setObjectName("PCBar")

        b_layout.addWidget(self.lbl_status)
        b_layout.addWidget(snap_lbl)
        b_layout.addSpacing(4)
        b_layout.addWidget(self.progress)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            PairCheckProgressDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#PCHeader {
                background: rgba(74, 222, 128, 35);
                border-bottom: 1px solid rgba(74, 222, 128, 25);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#PCBody {
                background: #131417;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QProgressBar#PCBar {
                background: rgba(74, 222, 128, 20);
                border: none;
                border-radius: 2px;
            }
            QProgressBar#PCBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(35, 166, 80, 220),
                    stop:1 rgba(94, 234, 149, 220)
                );
                border-radius: 2px;
            }
        """)

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % 4
        dots = "." * self._dots
        self.lbl_status.setText(f"Verificando alterações pendentes{dots}")

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)

    def showEvent(self, event):
        """Centraliza na tela primária ao exibir."""
        super().showEvent(event)
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + (geo.height() - self.height()) // 2,
            )


# ── Helper ────────────────────────────────────────────────────────────────────

class _ElideLabel(QLabel):
    """QLabel que trunca o texto com '…' no meio em vez de expandir a janela."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setMinimumWidth(0)

    def set_text(self, text: str) -> None:
        self._full_text = text
        self._update_elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elide()

    def _update_elide(self) -> None:
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full_text, Qt.ElideMiddle, self.width())
        super().setText(elided)
