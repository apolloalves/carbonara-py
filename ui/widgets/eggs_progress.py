from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QPlainTextEdit, QPushButton, QFrame, QWidget,
)


class EggsProgressDialog(QDialog):
    def __init__(self, title: str = "Penguin's Eggs", preparing_text: str = "Iniciando...", icon_glyph: str = "mdi6.egg-outline", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._preparing_text = preparing_text
        self._icon_glyph = icon_glyph
        self.setModal(True)
        self.setMinimumSize(1000, 700)
        self.resize(1060, 760)

        # Remove titlebar nativa — usamos header customizado. Qt.Window
        # (não Qt.Dialog) porque este dialog precisa ser maximizável —
        # muitos WMs recusam silenciosamente maximizar janelas do tipo
        # "Dialog". A causa real do empilhamento atrás do dock (ver
        # _toggle_maximize abaixo) nunca foi esse flag — era a sobrescrita
        # manual de geometria depois do showMaximized().
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        self._workers: list = []
        # Flag independente de _workers: cobre o período em que a operação
        # está tecnicamente "em andamento" mas ainda não existe nenhum
        # QThread rodando — ex: durante o painel de escolha de disco
        # alternativo (prompt_alternative_destination), que bloqueia com
        # um QEventLoop local antes de qualquer worker ser criado. Sem
        # essa flag, ESC escapava exatamente nessa janela de tempo.
        self._is_running = False
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

        # Buffer de log — descarrega no widget a cada 300ms para não afogar o event loop
        self._log_buffer: list[str] = []
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(300)
        self._log_flush_timer.timeout.connect(self._flush_log_buffer)
        self._log_flush_timer.start()

        # Para drag da janela sem titlebar
        self._drag_pos = None

        self._build_ui()
        self._apply_styles()
        self.log_view.viewport().setStyleSheet("background: rgba(0, 0, 0, 60);")

    def showEvent(self, event):
        """Centraliza na tela primária ao exibir — evita aparecer no monitor
        errado."""
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

        # Botão maximizar/restaurar — usa o mecanismo nativo do Qt
        # (showMaximized/showNormal) para o gerenciador de janelas (GNOME
        # Shell) reconhecer o estado corretamente (ex: esconder dock
        # com auto-hide quando a janela está maximizada de verdade).
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
        self._body_layout = body_layout

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
            EggsProgressDialog {
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
                color: #dce6f0;
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
                color: #dce6f0;
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
                background: transparent;
                border: 1px solid rgba(255,255,255,16);
                border-radius: 10px;
                color: #dce6f0;
                font-family: "DejaVu Sans Mono";
                font-size: 12px;
                line-height: 180%;
                padding: 10px;
                selection-background-color: rgba(35, 166, 255, 80);
            }
            QPlainTextEdit#BackupLog > QWidget {
                background: transparent;
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
                padding: 8px 24px;
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
        """Mata o processo eggs produce via PID e limpa /home/eggs com segurança."""
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Cancelando...")
        self.set_status("Cancelando operação...")
        self.set_current_file("—")
        self._had_failure = True

        # Cancela todos os ShellWorkers ativos
        for worker in list(self._workers):
            try:
                worker.cancel()
            except Exception:
                pass
        self._workers.clear()

        # Limpeza em thread separada (umount + rmtree pode demorar)
        from PySide6.QtCore import QThread, Signal as QSignal
        from core.eggs.eggs import _safe_remove_eggs_dir

        class _EggsCleanup(QThread):
            done_sig = QSignal()

            def run(self):
                _safe_remove_eggs_dir()
                self.done_sig.emit()

        self._cleanup_thread = _EggsCleanup(self)
        self._cleanup_thread.done_sig.connect(self._on_eggs_cleanup_done)
        self._cleanup_thread.start()

    def _on_eggs_cleanup_done(self) -> None:
        self.lbl_status.setText("Operação cancelada pelo usuário.")
        self.lbl_status.setStyleSheet("color: #ffb86b; font-weight: bold;")
        self.append_log("")
        self.append_log("--- Operação cancelada. Diretório /home/eggs removido. ---")
        self._timer_active = False
        self._elapsed_timer.stop()
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)
        # Forçar flush do buffer antes de finalizar
        self._flush_log_buffer()

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
        """Usa o maximize nativo do Qt (showMaximized/showNormal) puro,
        confiando inteiramente no gerenciador de janelas. A versão antiga
        deste método evitava showMaximized() e fazia setGeometry manual
        porque um diagnóstico anterior (errado) achava que o estado
        "maximizado" nativo é que empilhava a janela atrás do dock — na
        real, era a própria sobrescrita manual de geometria que causava
        isso, confirmado ao corrigir o mesmo bug no ClonezillaProgressDialog.
        O showMaximized() nativo já maximiza corretamente no monitor onde
        a janela está no momento, sem precisar de screenAt() manual."""
        if self.isMaximized():
            self.showNormal()
            self._btn_header_maximize.setIcon(qta.icon("mdi6.window-maximize", color="#9aa6b2"))
            self._btn_header_maximize.setToolTip("Maximizar")
        else:
            self.showMaximized()
            self._btn_header_maximize.setIcon(qta.icon("mdi6.window-restore", color="#9aa6b2"))
            self._btn_header_maximize.setToolTip("Restaurar")

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
            if any(text.startswith(p) for p in ("ERRO:", "ERRO ", "✗")):
                color = "#ff8888"
            elif any(text.startswith(p) for p in ("✓", "--- ", "=== ")):
                color = "#9bf0bd"
            elif text.startswith("INFO:"):
                color = "#8fd4ff"
            elif text.startswith("INICIANDO:"):
                color = "#ffda6b"
            elif any(text.startswith(p) for p in ("AVISO:", "AVISO ", "  ✗")):
                color = "#ffb86b"
            elif text.startswith("$"):
                color = "#8fd4ff"
            elif text.startswith("Copiando:"):
                color = "#c8d4e0"
            elif text.startswith("Tempo decorrido:"):
                color = "#6b7a8d"
            elif not text.strip():
                color = "#000000"
            else:
                color = "#dce6f0"

            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            cursor.insertText(("\n" if cursor.position() > 0 else "") + text, fmt)

        self.log_view.setTextCursor(cursor)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def set_progress_percent(self, pct: int) -> None:
        """Troca a barra do modo indeterminado (setRange(0,0), só um
        segmento andando de um lado pro outro) pra uma barra real 0-100%
        assim que o primeiro percentual real chega (ex: parseado do
        xorriso) — antes ficava indeterminada a operação inteira, e se
        travasse não dava pra saber em qual etapa (70%? 90%?) sem rolar
        o log até achar a última linha."""
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self.progress.setValue(max(0, min(100, pct)))

    def set_title(self, text: str) -> None:
        """Texto central grande (ex: 'Instalando...') — antes só dava pra
        definir na criação do diálogo (preparing_text) e ficava preso
        naquilo pro resto da operação, mesmo quando o que realmente
        estava acontecendo mudava (ex: virava só uma checagem sem nada
        pra instalar)."""
        self.lbl_title.setText(text)

    def set_header_title(self, text: str) -> None:
        """Título mostrado na barra de cabeçalho customizada (frameless,
        sem titlebar nativa) — mesma limitação do set_title: antes só
        dava pra definir na criação."""
        self.setWindowTitle(text)
        self.lbl_header.setText(text)

    def set_current_file(self, text: str) -> None:
        self.lbl_current.set_text(f"Arquivo atual: {text}")

    def prompt_alternative_destination(self, candidates: list[dict], estimated_gb: float) -> str | None:
        """Mostra, na mesma janela (sem popup separado), uma lista de
        discos alternativos com espaço suficiente e espera o usuário
        escolher um ou cancelar. Bloqueia com um QEventLoop local — não
        precisa de dialog.exec() aninhado, já que a QApplication já existe
        nesse ponto (roda dentro do processo privilegiado do helper).
        Retorna o mountpoint escolhido, ou None se cancelado."""
        from PySide6.QtCore import QEventLoop

        if not self.isVisible():
            self.show()

        panel = QFrame()
        panel.setObjectName("AltDestPanel")
        panel.setStyleSheet("""
            QFrame#AltDestPanel {
                border: 1px solid rgba(255, 184, 107, 90);
                border-radius: 10px;
                background: rgba(255, 184, 107, 14);
            }
        """)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(10)

        title = QLabel(
            f"Espaço insuficiente no destino escolhido "
            f"(necessário ~{estimated_gb:.1f} GB). Escolha outro disco:"
        )
        title.setWordWrap(True)
        title.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        title.setStyleSheet("color: #ffb86b; background: transparent; border: none;")
        panel_layout.addWidget(title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        result = {"choice": None}
        loop = QEventLoop()

        def _make_pick(mountpoint: str):
            def _pick():
                result["choice"] = mountpoint
                loop.quit()
            return _pick

        for c in candidates:
            btn = QPushButton(f"{c['mountpoint']}\n{c['label']} • {c['free_gb']:.1f} GB livres")
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,8);
                    border: 1px solid rgba(255, 184, 107, 110);
                    border-radius: 8px;
                    color: #ecf4ff;
                    font-family: "DejaVu Sans Mono";
                    font-size: 9pt;
                    padding: 8px 14px;
                }
                QPushButton:hover {
                    background: rgba(255, 184, 107, 35);
                    border: 1px solid rgba(255, 184, 107, 200);
                }
            """)
            btn.clicked.connect(_make_pick(c["mountpoint"]))
            btn_row.addWidget(btn)

        panel_layout.addLayout(btn_row)

        # Insere logo acima do log — bem visível, sem atrapalhar o resto
        # do layout (barra de progresso, título, etc. continuam no lugar).
        log_index = self._body_layout.indexOf(self.log_view)
        self._body_layout.insertWidget(log_index, panel)

        # Espaçador dedicado entre o painel e o log — o body_layout tem
        # spacing=0 (as outras seções usam addSpacing() explícito em vez
        # de spacing padrão), então sem isso o painel encosta direto no
        # log. Criado e removido junto com o painel, sem sobrar órfão.
        spacer = QWidget()
        spacer.setFixedHeight(14)
        self._body_layout.insertWidget(log_index + 1, spacer)

        def _cancel_pick():
            result["choice"] = None
            loop.quit()

        # Sem botão de cancelar dentro do painel — reaproveita o Cancelar
        # do rodapé (já existente), conectado só enquanto o painel está
        # aberto. Nada de confirmação em 2 cliques aqui: cancelar a
        # escolha do disco não interrompe nada destrutivo em andamento.
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(_cancel_pick)
        self.btn_cancel.setEnabled(True)

        loop.exec()

        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        panel.deleteLater()
        spacer.deleteLater()
        return result["choice"]

    def _tick_elapsed(self) -> None:
        self._elapsed_seconds += 1
        h, rem = divmod(self._elapsed_seconds, 3600)
        m, s = divmod(rem, 60)
        text = f"{m:02d}:{s:02d}" if h == 0 else f"{h:02d}:{m:02d}:{s:02d}"
        self.lbl_elapsed.setText(text)

    def set_running(self, running: bool) -> None:
        self._is_running = running
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
        elapsed = self.lbl_elapsed.text()
        status = self.lbl_status.text()

        if self._had_failure:
            # Só exibe ERRO se não foi cancelamento intencional (status já foi setado no cancel)
            if "cancelada" not in status.lower():
                self.lbl_status.setStyleSheet("color: #ff8888; font-weight: bold;")
                self.append_log(f"ERRO: {status}")
                self.append_log(f"Tempo decorrido: {elapsed}")
        else:
            if "nenhuma atualização disponível" in status.lower():
                self.lbl_status.setStyleSheet("color: #ffb86b; font-weight: bold;")
            else:
                self.lbl_status.setStyleSheet("color: #9bf0bd; font-weight: bold;")
            self.append_log(f"✓ {status}")
            self.append_log(f"Tempo decorrido: {elapsed}")

        # Garante que as últimas linhas apareçam na hora, sem esperar o
        # próximo tick do timer de 300ms (a operação já terminou).
        self._flush_log_buffer()

    def closeEvent(self, event) -> None:
        if self._is_running or any(w.isRunning() for w in self._workers):
            event.ignore()
            self.set_status("Backup em execução. Use Cancelar para interromper.")
            return
        super().closeEvent(event)

    def reject(self) -> None:
        # QDialog trata ESC chamando reject() diretamente (via done()/hide()),
        # sem passar pelo closeEvent — por isso o "X" da janela já ficava
        # bloqueado com processo rodando, mas o ESC escapava e fechava o
        # diálogo sem avisar nada, deixando o worker órfão (foi assim que a
        # ISO em andamento se perdeu). Replica aqui a mesma trava do closeEvent.
        # Checa _is_running também, não só _workers: durante o painel de
        # escolha de disco alternativo ainda não existe worker nenhum, só
        # o QEventLoop local — sem isso o ESC escapava bem nessa janela.
        if self._is_running or any(w.isRunning() for w in self._workers):
            self.set_status("Backup em execução. Use Cancelar para interromper.")
            return
        super().reject()


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
