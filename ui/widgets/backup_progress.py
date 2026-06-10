from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QPlainTextEdit, QPushButton, QFrame,
)


class BackupProgressDialog(QDialog):
    def __init__(self, title: str = "Carbonara Backup", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(800, 560)

        # Remove titlebar nativa — usamos header customizado
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        self._workers: list = []
        self._cancel_countdown = 0
        self._cancel_timer = QTimer(self)
        self._cancel_timer.setInterval(1000)
        self._cancel_timer.timeout.connect(self._countdown_tick)

        # Para drag da janela sem titlebar
        self._drag_pos = None

        self._build_ui()
        self._apply_styles()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header customizado ───────────────────────────────────────────────
        self.header = QFrame()
        self.header.setObjectName("DialogHeader")
        self.header.setFixedHeight(52)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 0, 16, 0)
        header_layout.setSpacing(0)

        lbl_icon = QLabel()
        lbl_icon.setFixedSize(32, 32)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setPixmap(qta.icon("mdi6.harddisk", color="#ffffff").pixmap(20, 20))
        lbl_icon.setStyleSheet(
            "QLabel { background: rgba(35, 166, 255, 34); border-radius: 10px; }"
        )

        lbl_header = QLabel("Carbonara Backup")
        lbl_header.setObjectName("HeaderTitle")
        lbl_header.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))

        header_layout.addWidget(lbl_icon)
        header_layout.addSpacing(10)
        header_layout.addWidget(lbl_header)
        header_layout.addStretch(1)

        # Botão fechar no header (× apenas visual — só fecha se não estiver rodando)
        self._btn_header_close = QPushButton("✕")
        self._btn_header_close.setObjectName("HeaderClose")
        self._btn_header_close.setFixedSize(28, 28)
        self._btn_header_close.clicked.connect(self._on_header_close)
        header_layout.addWidget(self._btn_header_close)

        root.addWidget(self.header)

        # ── Corpo ────────────────────────────────────────────────────────────
        body = QFrame()
        body.setObjectName("DialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(0)

        # Status principal
        self.lbl_title = QLabel("Preparando snapshot...")
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
        body_layout.addSpacing(12)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("ProgressSep")
        body_layout.addWidget(sep)
        body_layout.addSpacing(8)

        # Log
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("BackupLog")
        body_layout.addWidget(self.log_view, stretch=1)
        body_layout.addSpacing(16)

        # Botões
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setMinimumWidth(130)
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        self.btn_close = QPushButton("Fechar")
        self.btn_close.setEnabled(False)
        self.btn_close.setFixedWidth(110)
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
                background: transparent;
            }

            /* ── Header ── */
            QFrame#DialogHeader {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(14, 22, 40, 255),
                    stop:1 rgba(10, 16, 30, 255)
                );
                border-bottom: 1px solid rgba(31, 92, 255, 120);
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

            QPushButton#HeaderClose {
                background: transparent;
                border: none;
                color: #4a5a6a;
                font-size: 13px;
                border-radius: 6px;
            }
            QPushButton#HeaderClose:hover {
                background: rgba(200, 60, 60, 60);
                color: #ff8888;
            }

            /* ── Body ── */
            QFrame#DialogBody {
                background: #080c14;
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

            QFrame#ProgressSep {
                border: none;
                border-top: 1px solid rgba(31, 92, 255, 55);
            }

            QProgressBar#BackupProgress {
                background-color: rgba(10, 15, 25, 230);
                border: 1px solid rgba(31, 92, 255, 120);
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
                    stop:0 rgba(31, 92, 255, 220),
                    stop:1 rgba(35, 166, 255, 220)
                );
                border-radius: 3px;
            }

            QPlainTextEdit#BackupLog {
                background-color: rgba(6, 9, 16, 240);
                border: 1px solid rgba(31, 92, 255, 55);
                border-radius: 10px;
                color: #c8d4e0;
                font-family: "DejaVu Sans Mono";
                font-size: 10px;
                padding: 8px;
                selection-background-color: rgba(35, 166, 255, 80);
            }

            QPushButton#BtnCancel {
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(200, 60, 60, 100);
                border-radius: 10px;
                color: #c8d4e0;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                padding: 6px 18px;
            }
            QPushButton#BtnCancel:hover {
                background: rgba(200, 60, 60, 40);
                border: 1px solid rgba(255, 100, 100, 180);
                color: #ffaaaa;
            }
            QPushButton#BtnCancel:disabled {
                color: #3a4a5a;
                border-color: rgba(200, 60, 60, 30);
                background: rgba(10, 15, 25, 100);
            }

            QPushButton#BtnClose {
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 10px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                padding: 6px 0;
            }
            QPushButton#BtnClose:hover {
                background: rgba(23, 147, 209, 70);
                border: 1px solid rgba(35, 166, 255, 180);
            }
            QPushButton#BtnClose:disabled {
                color: #3a4a5a;
                border-color: rgba(31, 92, 255, 30);
                background: rgba(10, 15, 25, 100);
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

    # ----------------------------------------------------------- public API --

    def register_worker(self, worker) -> None:
        self._workers.append(worker)
        worker.finished_ok.connect(lambda: self._cleanup_worker(worker))
        worker.failed.connect(lambda _: self._cleanup_worker(worker))

    def _cleanup_worker(self, worker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def set_current_file(self, text: str) -> None:
        self.lbl_current.set_text(f"Arquivo atual: {text}")

    def set_running(self, running: bool) -> None:
        self.btn_cancel.setEnabled(running)
        self.btn_close.setEnabled(not running)

    def closeEvent(self, event) -> None:
        if any(w.isRunning() for w in self._workers):
            event.ignore()
            self.set_status("Backup em execução. Use Cancelar para interromper.")
            return
        super().closeEvent(event)


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
