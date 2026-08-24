from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QDialog

from ui.pages.timeshift.timeshift_panel import SnapshotsPage, icon_badge, _SyncStatusBadge, _ScheduledSyncDialog
from core.i18n import tr


class BackupsPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet(
            """
            QWidget {
                background: transparent;
            }

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

            QLabel#HintLabel {
                color: #9aa6b2;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)

        from ui.main_window import AppHeaderBlock  # import adiado — evita import circular

        self.app_header = AppHeaderBlock(back_button=True)
        self.app_header.back_clicked.connect(self.back_requested.emit)
        root.addWidget(self.app_header)

        header = QFrame()
        header.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 14, 0, 0)
        header_layout.setSpacing(14)

        self.header_icon = icon_badge("mdi6.history", 48, color="#23a6ff", bg_rgba="35, 166, 255, 34")

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(2)

        title = QLabel("Timeshift")
        title.setFont(QFont("DejaVu Sans Mono", 22, QFont.Bold))
        title.setStyleSheet("color: #23a6ff;")

        subtitle = QLabel("Create, restore and verify Carbonara snapshots")
        subtitle.setFont(QFont("DejaVu Sans Mono", 10))
        subtitle.setStyleSheet("color: #9aa6b2;")

        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        header_layout.addWidget(self.header_icon)
        header_layout.addLayout(title_block)
        header_layout.addStretch(1)

        # ── Badge de sincronização automática — clique abre o diálogo
        # de configuração. Lê a config real salva em disco (persistida
        # pelo core/snapshots/scheduler.py) em vez de sempre começar do zero.
        from core.snapshots import scheduler as _scheduler_module
        self._scheduler = _scheduler_module
        self._sync_config: dict = self._scheduler.load_schedule_config()
        self.sync_badge = _SyncStatusBadge(self)
        self.sync_badge.clicked.connect(self._open_sync_dialog)
        header_layout.addWidget(self.sync_badge)
        self._refresh_sync_badge()

        # Guarda o último "last_run" visto — usado pelo timer abaixo pra
        # saber se um sync agendado terminou desde a última checagem
        self._last_seen_sync_run = self._scheduler.load_schedule_status().get("last_run")

        self.snapshots_page = SnapshotsPage(self)

        footer = QFrame()
        footer.setStyleSheet("background: transparent; border: none;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(0)

        footer_hint = QLabel("Back to menu: button or Esc")
        footer_hint.setObjectName("HintLabel")
        footer_hint.setFont(QFont("DejaVu Sans Mono", 9))
        footer_hint.setAlignment(Qt.AlignCenter)

        footer_layout.addWidget(footer_hint)

        root.addWidget(header)
        root.addWidget(self.snapshots_page, 1)
        root.addWidget(footer)

        # ── Toast de conclusão de sync automático — reaproveita a mesma
        # linguagem visual do toast de "Executando: ..." já usado no
        # Eggs (card escuro 420px, borda azul), mas sem spinner (aqui
        # o sync já TERMINOU quando detectamos, não tem nada rodando
        # pra animar) e some sozinho depois de alguns segundos.
        self._sync_toast = QFrame(self)
        self._sync_toast.setObjectName("SyncCompletedToast")
        self._sync_toast.setFixedWidth(420)
        self._sync_toast.setStyleSheet("""
            QFrame#SyncCompletedToast {
                background: rgba(15, 18, 28, 235);
                border: 1px solid rgba(35, 166, 255, 110);
                border-radius: 12px;
            }
            QLabel { background: transparent; }
        """)
        toast_layout = QHBoxLayout(self._sync_toast)
        toast_layout.setContentsMargins(18, 14, 18, 14)
        toast_layout.setSpacing(12)

        self._sync_toast_icon = QLabel()
        self._sync_toast_icon.setFixedSize(20, 20)
        self._sync_toast_label = QLabel("")
        self._sync_toast_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        self._sync_toast_label.setStyleSheet("color: #ecf4ff;")
        self._sync_toast_label.setWordWrap(True)

        toast_layout.addWidget(self._sync_toast_icon)
        toast_layout.addWidget(self._sync_toast_label, 1)

        self._sync_toast.hide()
        self._sync_toast.adjustSize()

        self._sync_toast_hide_timer = QTimer(self)
        self._sync_toast_hide_timer.setSingleShot(True)
        self._sync_toast_hide_timer.timeout.connect(self._sync_toast.hide)

        # ── Verifica periodicamente se um sync agendado terminou em
        # segundo plano enquanto esta tela estava aberta. O sync
        # agendado roda num processo systemd totalmente separado da
        # GUI — sem isso, a lista de snapshots só atualiza quando você
        # sai da página e volta (showEvent), o que não ajuda se você
        # ficou parado exatamente nesta tela esperando o horário chegar.
        self._sync_poll_timer = QTimer(self)
        self._sync_poll_timer.timeout.connect(self._check_scheduled_sync_update)
        self._sync_poll_timer.start(30_000)  # 30s — leve o bastante pra não incomodar

    def _reposition_sync_toast(self) -> None:
        self._sync_toast.adjustSize()
        margin = 24
        top_margin = 90
        x = self.width() - self._sync_toast.width() - margin
        self._sync_toast.move(max(margin, x), top_margin)
        self._sync_toast.raise_()

    def _show_sync_toast(self, text: str, icon_glyph: str, icon_color: str) -> None:
        self._sync_toast_icon.setPixmap(qta.icon(icon_glyph, color=icon_color).pixmap(20, 20))
        self._sync_toast_label.setText(text)
        self._sync_toast.show()
        self._reposition_sync_toast()
        self._sync_toast_hide_timer.start(6_000)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._sync_toast.isVisible():
            self._reposition_sync_toast()

    def _check_scheduled_sync_update(self) -> None:
        status = self._scheduler.load_schedule_status()
        last_run = status.get("last_run")
        if last_run and last_run != self._last_seen_sync_run:
            self._last_seen_sync_run = last_run
            self._refresh_sync_badge()
            self.snapshots_page.refresh_destinations()

            result = status.get("last_result")
            if result == "success":
                kinds = ", ".join(status.get("synced_kinds") or [])
                self._show_sync_toast(
                    tr("snapshots.sync_toast_success").format(kinds=kinds or "—"),
                    "mdi6.check-circle-outline", "#34d399",
                )
            elif result == "failed":
                self._show_sync_toast(
                    tr("snapshots.sync_toast_failed"),
                    "mdi6.alert-circle-outline", "#ff8888",
                )
            elif result == "nothing_to_sync":
                # Diferente de "skipped" — aqui o agendamento está ativo
                # mas não há nenhum snapshot pra sincronizar, então nada
                # está sendo protegido de verdade. Silêncio aqui seria
                # enganoso (o badge sozinho mostraria "ativado" com
                # confiança total).
                self._show_sync_toast(
                    tr("snapshots.sync_toast_nothing"),
                    "mdi6.alert-outline", "#e0a840",
                )
            # "skipped" (outra operação em andamento) continua sem toast —
            # esse sim é passageiro, sem problema real

    def _refresh_sync_badge(self) -> None:
        enabled = self._sync_config.get("enabled", False)
        next_run = self._scheduler.next_run_display(self._sync_config) if enabled else None
        self.sync_badge.set_state(enabled=enabled, next_run=next_run)

    def _open_sync_dialog(self) -> None:
        # Injeta o destino atualmente selecionado na tela — o sync
        # agendado precisa saber ONDE sincronizar, já que roda sem
        # ninguém pra escolher isso na hora
        dest = self.snapshots_page.current_destination()
        if dest is not None:
            self._sync_config["destination_mountpoint"] = dest.mountpoint

        dialog = _ScheduledSyncDialog(self._sync_config, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._sync_config = dialog.result_config
            self._refresh_sync_badge()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.back_requested.emit()
            return
        super().keyPressEvent(event)

