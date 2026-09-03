from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List
import json
import os
import shutil
import subprocess
import tempfile
import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QThread, QObject, QEvent, QPoint, QTime, QRect
from PySide6.QtGui import QFont, QColor, QFontMetrics

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QFrame,
    QComboBox,
    QListView,
    QScrollArea,
    QSizePolicy,
    QDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QAbstractItemView,
    QSplitter,
    QProgressBar,
    QPlainTextEdit,
    QCheckBox,
    QGraphicsDropShadowEffect,
    QTimeEdit,
    QLineEdit,
)

from core.operation_manager import OperationManager
from core.i18n import tr, i18n
from core.system.storage import (
    StorageDestination,
    format_gb,
    list_backup_destinations,
)

#Material Icons
DEST_GLYPH      = "mdi6.harddisk"
ROOT_GLYPH      = ""
HOME_GLYPH      = ""
BOTH_GLYPH      = ""

RESTORE_GLYPH   = "mdi6.file-restore-outline"
SYNC_GLYPH      = "mdi6.sync"
DELETE_GLYPH    = "mdi6.delete"

REFRESH_GLYPH   = "mdi6.refresh"
CREATE_GLYPH    = "mdi6.folder-multiple"


def _checkbox_check_icon_path() -> str:
    """Gera (uma vez só, em cache) um PNG com o ícone de "visto" pra usar
    dentro do indicador do checkbox marcado — QSS puro não desenha ícone
    ali, só cor/borda, então precisa de um arquivo de imagem de verdade
    referenciado via `image: url(...)`."""
    cache_path = Path(tempfile.gettempdir()) / "carbonara_checkbox_check.png"
    if not cache_path.exists():
        qta.icon("mdi6.check-bold", color="#08111d").pixmap(16, 16).save(str(cache_path))
    return str(cache_path).replace("\\", "/")
VERIFY_GLYPH    = "mdi6.magnify-scan"

SNAPSHOT_GLYPH  = "mdi6.archive"



@dataclass(frozen=True)
class SnapshotEntry:
    kind: str
    path: Path
    meta_text: str
    modified_text: str
    size_str: str = ""
    size_gb: float = 0.0
    synced_at: str = ""
    created_at: str = ""


def read_snapshot_metadata(path: Path) -> dict:
    meta_file = path / "snapshot.json"
    if not meta_file.exists():
        return {}

    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def collect_snapshots(backup_root: Path) -> List[SnapshotEntry]:
    entries: List[SnapshotEntry] = []

    if not backup_root.exists():
        return entries

    for kind_dir in backup_root.iterdir():
        if not kind_dir.is_dir():
            continue

        for snap in sorted(
            [p for p in kind_dir.iterdir() if p.is_dir() and p.name != "latest"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                stat = snap.stat()
                meta = read_snapshot_metadata(snap)

                created_at = meta.get("created_at") or datetime.fromtimestamp(
                    stat.st_mtime
                ).strftime("%Y-%m-%d %H:%M:%S")

                # created_at pode vir em dois formatos: ISO com "T" (da
                # metadata gravada pelo backup.py) ou "YYYY-MM-DD HH:MM:SS"
                # (fallback do mtime do arquivo, sem metadata). Normaliza
                # pro formato com "T" — mesmo formato de synced_at — pra
                # poder ser usado como fallback dele mais abaixo, sem
                # precisar tratar dois formatos na hora de exibir a badge.
                created_at_iso = created_at.replace(" ", "T", 1) if " " in created_at else created_at

                status = meta.get("status", "unknown")

                # Ignora snapshots incompletos (processo cancelado ou travado)
                if status in ("running", "failed"):
                    continue

                source = meta.get("source", "")
                size_bytes = meta.get("size_bytes", 0)
                size_str = ""
                size_gb = 0.0
                if size_bytes and size_bytes > 0:
                    size_gb = size_bytes / (1024 ** 3)
                    if size_gb >= 1:
                        size_str = f"{size_gb:.1f} GB"
                    else:
                        size_str = f"{size_bytes / (1024 ** 2):.0f} MB"

                meta_text = f"{created_at} • {status}"
                if source:
                    meta_text = f"{meta_text} • {source}"

                synced_at = meta.get("synced_at", "")

                entries.append(
                    SnapshotEntry(
                        kind=kind_dir.name,
                        path=snap,
                        meta_text=meta_text,
                        modified_text=datetime.fromtimestamp(
                            stat.st_mtime
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                        size_str=size_str,
                        size_gb=size_gb,
                        synced_at=synced_at,
                        created_at=created_at_iso,
                    )
                )
            except OSError:
                continue

    return entries


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()

        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)
            child_layout.deleteLater()

def icon_badge(icon_name: str, size: int = 34, color: str = "#FFFFFF", bg_rgba: str = "35, 166, 255, 34", opacity: float = 1.0) -> QLabel:
    label = QLabel()
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(size, size)

    icon_color = QColor(color)
    icon_color.setAlpha(int(max(0.0, min(1.0, opacity)) * 255))

    pixmap = qta.icon(
        icon_name,
        color=icon_color
    ).pixmap(size - 2, size - 2)

    label.setPixmap(pixmap)

    label.setStyleSheet(
        f"""
        QLabel {{
            background: rgba({bg_rgba});
            border-radius: 10px;
        }}
        """
    )

    return label

def style_combo_popup(combo: QComboBox) -> None:
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


class ScopeCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, title: str, subtitle: str, glyph: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._glyph = glyph

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(96)
        self.setProperty("active", False)

        self.setStyleSheet(
            """
            QFrame {
                background: transparent;
                border: none;
            }

            QPushButton {
                background: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 12px;
                color: #c8d4e0;
                font: 700 9pt "DejaVu Sans Mono";
                padding: 0px 12px;
                min-height: 34px;
            }

            QPushButton:hover {
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 22);
                color: #c8d4e0;
            }

            QPushButton:checked {
                background: rgba(59, 130, 246, 0.22);
                border: 1px solid rgba(99, 140, 255, 130);
                color: #ffffff;
            }

            QLabel#ScopeSubtitle {
                color: #5a6a7a;
                background: transparent;
                border: none;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)

        self.btn = QPushButton(f"{glyph}  {title}")
        self.btn.setMinimumHeight(44)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setFocusPolicy(Qt.StrongFocus)
        self.btn.setCheckable(True)
        self.btn.clicked.connect(self._emit_clicked)

        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("ScopeSubtitle")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setFont(QFont("DejaVu Sans Mono", 9))
        self.subtitle.setWordWrap(False)
        self.subtitle.setToolTip(subtitle)
        self.subtitle.setTextInteractionFlags(Qt.NoTextInteraction)

        root.addWidget(self.btn)
        root.addWidget(self.subtitle)

    def _emit_clicked(self):
        self.clicked.emit(self.key)

    def set_text(self, title: str, subtitle: str) -> None:
        self.btn.setText(f"{self._glyph}  {title}")
        self.subtitle.setText(subtitle)
        self.subtitle.setToolTip(subtitle)

    def set_active(self, active: bool):
        self.btn.setChecked(active)
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.btn.click()
            self.clicked.emit(self.key)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.btn.click()
            self.clicked.emit(self.key)
            event.accept()
            return
        super().keyPressEvent(event)


class _TopTooltipFilter(QObject):
    """Tooltip estilo toast pros botões RESTORE/SYNC/DELETE — substitui o
    QToolTip nativo do Qt (que tinha cache de reexibição inconsistente:
    'aparece quando quer'). Delega a exibição pra página (SnapshotsPage),
    que tem seu próprio toast QFrame (self._button_toast) — filho real da
    página, igual ao operation_status_row do eggs_page.py, em vez de uma
    janela topo-nível própria (Qt.ToolTip) como na primeira tentativa, que
    o compositor/mutter custom do Apollo não renderizava direito
    (transparência/cantos arredondados saíam errados)."""
    def __init__(self, page: QWidget, parent=None):
        super().__init__(parent)
        self._page = page

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip and obj.toolTip():
            self._page._show_button_toast(obj, obj.toolTip())
            return True
        if event.type() == QEvent.Leave:
            self._page._hide_button_toast()
        return super().eventFilter(obj, event)



class SnapshotCard(QFrame):
    def __init__(self, entry: SnapshotEntry, sibling: "SnapshotEntry | None" = None, page: QWidget = None, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._page = page

        self.setObjectName("SnapshotCard")
        self.setStyleSheet(
            """
            QFrame#SnapshotCard {
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 14px;
                background: rgba(255, 255, 255, 6);
            }
            QFrame#SnapshotCard:hover {
                border: 1px solid rgba(255, 255, 255, 22);
                background: rgba(255, 255, 255, 9);
            }

            QPushButton {
                padding: 0px 22px;
                border-radius: 9px;
                border: 1px solid rgba(255, 255, 255, 14);
                background: rgba(255, 255, 255, 6);
                color: #c8d4e0;
                font: 700 9pt "DejaVu Sans Mono";
                min-height: 34px;
            }

            QPushButton:hover {
                background: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 28);
                color: #ecf4ff;
            }

            QPushButton#DangerButton {
                border: 1px solid rgba(200, 60, 60, 100);
                color: #c8d4e0;
            }

            QPushButton#DangerButton:hover {
                background: rgba(200, 60, 60, 40);
                border: 1px solid rgba(255, 100, 100, 180);
                color: #ffaaaa;
            }

            QPushButton#RestoreButton {
                border: 1px solid rgba(35, 166, 255, 110);
                color: #c8d4e0;
            }

            QPushButton#RestoreButton:hover {
                background: rgba(35, 166, 255, 40);
                border: 1px solid rgba(70, 188, 255, 200);
                color: #8fd4ff;
            }

            QPushButton#SyncButton {
                border: 1px solid rgba(74, 222, 128, 100);
                color: #c8d4e0;
            }

            QPushButton#SyncButton:hover {
                background: rgba(74, 222, 128, 35);
                border: 1px solid rgba(94, 234, 149, 200);
                color: #9bf0bd;
            }
            """
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(18)

        left = QHBoxLayout()
        left.setSpacing(16)

        # Ícone de volta, mas em branco-suave (não branco puro, pra não
        # ficar forte) em vez das cores por accent (azul/âmbar) usadas
        # antes — pedido explícito após rejeitar todas as variações de
        # opacidade sobre a cor de destaque.
        icon_label = icon_badge(
            SNAPSHOT_GLYPH, 46,
            color="#f0f2f5", bg_rgba="255, 255, 255, 14",
            opacity=0.9,
        )

        text_block = QVBoxLayout()
        text_block.setSpacing(6)

        title = QLabel(entry.path.name)
        title_font = QFont("DejaVu Sans Mono")
        title_font.setPointSizeF(10.5)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ecf4ff;")

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(title)

        # Badge de recência — quantos dias desde o último sync deste
        # snapshot específico. Isso é matemática pura sobre uma data já
        # conhecida (sem heurística de comparação com o irmão, que sempre
        # dava falso positivo). Passado STALE_AFTER_DAYS, fica âmbar como
        # lembrete. A checagem 100% real continua sendo o dry-run, seja
        # via SYNC individual ou via o botão VERIFICAR (checa os dois).
        STALE_AFTER_DAYS = 7
        # Fallback: snapshots feitos ANTES desse dia (synced_at só passou
        # a ser gravado na criação, não só no SYNC explícito) ou qualquer
        # entrada sem synced_at por algum outro motivo — um snapshot
        # recém-criado já nasce em sincronia com o sistema no momento em
        # que foi feito, então created_at é um fallback válido, não um
        # "nunca". Só cai em "nunca sincronizado" se faltarem os dois.
        sync_reference = entry.synced_at or entry.created_at
        if sync_reference:
            try:
                self_dt = datetime.strptime(sync_reference, "%Y-%m-%dT%H:%M:%S")
                # Compara datas de calendário, não 24h corridas — se
                # sincronizou às 08:41 do dia 28 e você abre antes das
                # 08:41 do dia 29, timedelta.days ainda dá 0 (não
                # completou 24h), mas já é "ontem" no calendário.
                elapsed_days = (datetime.now().date() - self_dt.date()).days
            except ValueError:
                elapsed_days = None

            if elapsed_days is not None:
                if elapsed_days <= 0:
                    badge_text = tr("snapshots.synced_today")
                elif elapsed_days == 1:
                    badge_text = tr("snapshots.synced_1_day")
                else:
                    badge_text = tr("snapshots.synced_n_days").format(n=elapsed_days)

                stale = elapsed_days > STALE_AFTER_DAYS
                badge_color = "#e0a840" if stale else "#5eea95"
                badge_bg = "rgba(224,168,64,0.14)" if stale else "rgba(74,222,128,0.14)"

                badge = QLabel(badge_text)
                badge.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
                badge.setStyleSheet(
                    f"color: {badge_color}; background: {badge_bg}; "
                    f"border-radius: 10px; padding: 4px 14px;"
                )
                title_row.addWidget(badge)
        else:
            # Antes, sem synced_at, nenhuma badge aparecia — dava a
            # impressão de que a informação de sync tinha sumido, quando
            # na verdade só significa "ainda não sincronizado nenhuma
            # vez". Mostra isso explicitamente em vez de ficar mudo.
            badge = QLabel(tr("snapshots.never_synced"))
            badge.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
            badge.setStyleSheet(
                "color: #ff9966; background: rgba(255,153,102,0.14); "
                "border-radius: 10px; padding: 4px 14px;"
            )
            title_row.addWidget(badge)

        title_row.addStretch()

        # Linha de meta + tamanho em destaque
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        meta_row.setContentsMargins(0, 0, 0, 0)

        meta = QLabel(entry.meta_text)
        meta.setFont(QFont("DejaVu Sans Mono", 10))
        meta.setStyleSheet("color: #6b7a8d;")
        meta_row.addWidget(meta)

        if entry.size_str:
            size_prefix = QLabel(tr("snapshots.size_label"))
            size_prefix.setFont(QFont("DejaVu Sans Mono", 9))
            size_prefix.setStyleSheet("color: #6b7a8d;")
            meta_row.addWidget(size_prefix)

            size_val = QLabel(entry.size_str)
            size_val.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
            size_val.setStyleSheet("color: #4ade80;")
            meta_row.addWidget(size_val)

        meta_row.addStretch()

        text_block.addLayout(title_row)
        text_block.addLayout(meta_row)

        # Linha synced_at — só aparece se já foi sincronizado
        if entry.synced_at:
            sync_row = QHBoxLayout()
            sync_row.setSpacing(6)
            sync_row.setContentsMargins(0, 0, 0, 0)

            sync_icon = QLabel()
            sync_icon.setPixmap(
                qta.icon(SYNC_GLYPH, color="#23a6ff").pixmap(14, 14)
            )
            sync_lbl = QLabel(tr("snapshots.last_sync").format(date=entry.synced_at.replace('T', 'T ', 1)))
            sync_lbl.setFont(QFont("DejaVu Sans Mono", 9))
            sync_lbl.setStyleSheet("color: #23a6ff;")

            sync_row.addWidget(sync_icon)
            sync_row.addWidget(sync_lbl)
            sync_row.addStretch()
            text_block.addLayout(sync_row)

        left.addWidget(icon_label)
        left.addLayout(text_block)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_restore = QPushButton()
        self.btn_restore.setIcon(qta.icon(RESTORE_GLYPH, color="#8fd4ff"))
        self.btn_restore.setIconSize(QSize(22, 22))
        self.btn_restore.setObjectName("RestoreButton")
        self.btn_restore.setToolTip(tr("snapshots.tooltip_restore"))
        self.btn_restore.setFixedWidth(48)

        self.btn_sync = QPushButton()
        self.btn_sync.setIcon(qta.icon(SYNC_GLYPH, color="#9bf0bd"))
        self.btn_sync.setIconSize(QSize(18, 18))
        self.btn_sync.setObjectName("SyncButton")
        self.btn_sync.setToolTip(tr("snapshots.tooltip_sync"))
        self.btn_sync.setFixedWidth(48)

        self.btn_delete = QPushButton()
        self.btn_delete.setIcon(qta.icon(DELETE_GLYPH, color="#ff8888"))
        self.btn_delete.setIconSize(QSize(18, 18))
        self.btn_delete.setObjectName("DangerButton")
        self.btn_delete.setToolTip(tr("snapshots.tooltip_delete"))
        self.btn_delete.setFixedWidth(48)

        btn_row.addWidget(self.btn_restore)
        btn_row.addWidget(self.btn_sync)
        btn_row.addWidget(self.btn_delete)

        self._tooltip_filter = _TopTooltipFilter(self._page)
        self.btn_restore.installEventFilter(self._tooltip_filter)
        self.btn_sync.installEventFilter(self._tooltip_filter)
        self.btn_delete.installEventFilter(self._tooltip_filter)

        root.addLayout(left, 1)
        root.addLayout(btn_row)


class SectionCard(QFrame):
    def __init__(self, title_text: str, path_text: str, glyph: str, accent_color: str = "#1f8dda", parent=None):
        super().__init__(parent)
        self.setObjectName("SectionCard")
        self.setStyleSheet(
            """
            QFrame#SectionCard {
                border: none;
                border-radius: 0px;
                background: transparent;
            }
            """
        )

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(8)

        head_frame = QFrame()
        head_frame.setObjectName("SectionHeader")
        head_frame.setStyleSheet(
            f"""
            QFrame#SectionHeader {{
                border: none;
                border-radius: 0px;
                background: transparent;
            }}
            """
        )
        head_layout = QHBoxLayout(head_frame)
        head_layout.setContentsMargins(12, 4, 0, 4)
        head_layout.setSpacing(10)

        labels = QVBoxLayout()
        labels.setSpacing(1)

        title = QLabel(title_text)
        title.setFont(QFont("DejaVu Sans Mono", 15, QFont.Bold))
        title.setStyleSheet(f"color: {accent_color};")

        path = QLabel(path_text)
        path.setFont(QFont("DejaVu Sans Mono", 8))
        path.setStyleSheet("color: #6b7a8d;")

        labels.addWidget(title)
        labels.addWidget(path)

        head_layout.addLayout(labels)
        head_layout.addStretch(1)

        # Divisor sólido, mas suavizado (opacidade reduzida) — cor cheia
        # ficava forte demais; com alpha ~55% fica visível o bastante pra
        # separar os grupos sem gritar na tela.
        r = int(accent_color[1:3], 16)
        g = int(accent_color[3:5], 16)
        b = int(accent_color[5:7], 16)
        divider = QFrame()
        divider.setFixedHeight(2)
        divider.setStyleSheet(f"background: rgba({r}, {g}, {b}, 50); border: none;")

        self.body = QGridLayout()
        self.body.setHorizontalSpacing(14)
        self.body.setVerticalSpacing(10)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setColumnStretch(0, 1)
        self.body.setColumnStretch(1, 1)
        self._card_count = 0

        self.layout_main.addWidget(head_frame)
        self.layout_main.addWidget(divider)
        self.layout_main.addSpacing(4)
        self.layout_main.addLayout(self.body)

    def add_card(self, card_widget) -> None:
        """Coloca os cards de snapshot em grade de 2 colunas — conforme
        mais snapshots forem criados, eles vão preenchendo pelo menos
        2 por linha em vez de empilhar um embaixo do outro."""
        row = self._card_count // 2
        col = self._card_count % 2
        self.body.addWidget(card_widget, row, col)
        self._card_count += 1


class SnapshotsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.entries: list[SnapshotEntry] = []
        self.destinations: list[StorageDestination] = []
        self._backup_proc: subprocess.Popen | None = None
        self.scope = "both"
        self.scope_cards: dict[str, ScopeCard] = {}

        # Rastreiam a operação em andamento para permitir oferecer
        # sincronizar o snapshot irmão (ROOT/HOME) ao concluir um sync.
        self._current_op_kind: str | None = None
        self._sync_entry: SnapshotEntry | None = None
        self._offer_pair_after_sync: bool = True
        self._pair_check_path: Path | None = None
        self._verify_check_path: Path | None = None
        self._verify_entries: dict[str, SnapshotEntry] = {}
        self._sync_queue: list[SnapshotEntry] = []

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_backup_process)

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

            QPushButton#PrimaryButton {
                background: rgba(74, 222, 128, 0.88);
                border: 1px solid rgba(74, 222, 128, 1);
                color: #08111d;
                font-weight: bold;
            }

            QPushButton#PrimaryButton:hover {
                background: rgba(94, 234, 149, 1);
                border: 1px solid rgba(94, 234, 149, 1);
            }

            QComboBox {
                background: rgba(10, 15, 25, 230);
                color: #ecf4ff;
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 10px;
                padding: 8px 12px;
                min-height: 28px;
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

            QLabel#Muted {
                color: #9aa6b2;
            }

            QScrollArea {
                border: none;
                background: transparent;
            }

            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            """
        )

        # Chevron do QComboBox — usa um ícone renderizado via qtawesome
        # (cacheado em disco) em vez do truque de borda CSS, que não
        # renderiza de forma confiável no Qt.
        chevron_path = Path(tempfile.gettempdir()) / "carbonara_chevron_down_v2.png"
        if not chevron_path.exists():
            qta.icon("mdi6.chevron-down", color="#23a6ff").pixmap(28, 28).save(str(chevron_path))
        self.setStyleSheet(
            self.styleSheet()
            + "QComboBox::down-arrow { image: url(" + chevron_path.as_posix() + "); "
            + "width: 14px; height: 14px; margin-right: 10px; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.control_card = QFrame()
        self.control_card.setObjectName("ControlCard")
        self.control_card.setStyleSheet(
            """
            QFrame#ControlCard {
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 18px;
                background: rgba(255, 255, 255, 6);
            }
            """
        )
        control_layout = QHBoxLayout(self.control_card)
        control_layout.setContentsMargins(20, 18, 20, 18)
        control_layout.setSpacing(48)
        control_layout.setAlignment(Qt.AlignTop)

        # ── COLUNA ESQUERDA ──
        left_panel = QVBoxLayout()
        left_panel.setSpacing(14)

        destination_block = QVBoxLayout()
        destination_block.setSpacing(8)

        lbl_destination = self.lbl_destination = QLabel(tr("snapshots.destination_label"))
        lbl_destination.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl_destination.setStyleSheet("color: #ecf4ff;")

        self.cmb_destination = QComboBox()
        self.cmb_destination.setEditable(False)
        self.cmb_destination.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_destination.setMaxVisibleItems(8)
        self.cmb_destination.setFocusPolicy(Qt.StrongFocus)
        self.cmb_destination.setView(QListView())
        self.cmb_destination.currentIndexChanged.connect(self._on_destination_changed)
        self.cmb_destination.activated[int].connect(self._on_destination_activated)
        style_combo_popup(self.cmb_destination)

        destination_block.addWidget(lbl_destination)
        destination_block.addWidget(self.cmb_destination)

        scope_block = QVBoxLayout()
        scope_block.setSpacing(10)
        scope_block.setContentsMargins(0, -4, 0, 0)

        lbl_scope = self.lbl_scope = QLabel(tr("snapshots.scope_label"))
        lbl_scope.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl_scope.setStyleSheet("color: #ecf4ff;")

        scope_cards_row = QHBoxLayout()
        scope_cards_row.setSpacing(10)

        scope_defs = [
            ("root", tr("snapshots.scope_root_title"), tr("snapshots.scope_root_subtitle"), ROOT_GLYPH),
            ("home", tr("snapshots.scope_home_title"), tr("snapshots.scope_home_subtitle"), HOME_GLYPH),
            ("both", tr("snapshots.scope_both_title"), tr("snapshots.scope_both_subtitle"), BOTH_GLYPH),
        ]

        for key, title, subtitle, glyph in scope_defs:
            card = ScopeCard(key, title, subtitle, glyph)
            card.clicked.connect(self.set_scope)
            self.scope_cards[key] = card
            scope_cards_row.addWidget(card)

        scope_block.addWidget(lbl_scope)
        scope_block.addLayout(scope_cards_row)

        left_panel.addLayout(destination_block)
        left_panel.addLayout(scope_block)

        # ── COLUNA DIREITA ──
        self.right_frame = QFrame()
        self.right_frame.setObjectName("RightPanel")
        self.right_frame.setStyleSheet(
            """
            QFrame#RightPanel {
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 16px;
                background: rgba(255, 255, 255, 6);
            }
            """
        )

        right_panel = QVBoxLayout(self.right_frame)
        right_panel.setContentsMargins(16, 14, 16, 14)
        right_panel.setSpacing(2)

        top_summary = QHBoxLayout()
        top_summary.setSpacing(8)
        top_summary.setAlignment(Qt.AlignVCenter)

        self.destination_badge = icon_badge(DEST_GLYPH, 52)

        summary_text = QVBoxLayout()
        summary_text.setSpacing(0)

        self.lbl_destination_info = QLabel(tr("snapshots.select_destination"))
        self.lbl_destination_info.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        self.lbl_destination_info.setStyleSheet("color: #ecf4ff;")

        self.lbl_destination_meta = QLabel("—")
        self.lbl_destination_meta.setObjectName("Muted")
        self.lbl_destination_meta.setStyleSheet("color: #9aa6b2; margin-top: -1px;")
        self.lbl_destination_meta.setFont(QFont("DejaVu Sans Mono", 9))

        summary_text.addWidget(self.lbl_destination_info)
        summary_text.addWidget(self.lbl_destination_meta)

        top_summary.addWidget(self.destination_badge, 0, Qt.AlignVCenter)
        top_summary.addLayout(summary_text)
        top_summary.addStretch()

        self.space_bar = QFrame()
        self.space_bar.setFixedHeight(5)
        self.space_bar.setStyleSheet("""
        QFrame {
            border: none;
            border-radius: 3px;
            background: rgba(255,255,255,18);
        }
        """)

        self.space_fill = QFrame(self.space_bar)
        self.space_fill.setGeometry(0, 0, 0, 5)
        self.space_fill.setStyleSheet("""
        QFrame {
            border: none;
            border-radius: 3px;
            background: rgba(35,166,255,210);
        }
        """)

        self.lbl_space_percent = QLabel("—")
        self.lbl_space_percent.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        self.lbl_space_percent.setStyleSheet("color: #4ade80;")

        space_row = QHBoxLayout()
        space_row.setSpacing(10)
        space_row.setContentsMargins(0, 8, 0, 0)
        space_row.addWidget(self.space_bar, 8)
        space_row.addWidget(self.lbl_space_percent, 1)

        right_panel.addLayout(top_summary)
        right_panel.addLayout(space_row)

        # botões FORA do right_frame
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(12)

        self.btn_refresh = QPushButton(tr("snapshots.btn_refresh_space"))
        self.btn_refresh.setIcon(qta.icon(REFRESH_GLYPH, color="#FFFFFF"))
        self.btn_refresh.setIconSize(QSize(16, 16))
        self.btn_refresh.setFixedSize(190, 40)
        self.btn_refresh.setVisible(True)  # reabilitado: útil para recalcular espaço após mudanças fora do app

        self.btn_create = QPushButton(tr("snapshots.btn_create_snapshot"))
        self.btn_create.setIcon(qta.icon(CREATE_GLYPH))
        self.btn_create.setIconSize(QSize(16, 16))
        self.btn_create.setFixedSize(160, 40)
        self.btn_create.setObjectName("PrimaryButton")

        self.btn_refresh.clicked.connect(self.refresh_destinations)
        self.btn_create.clicked.connect(self.create_snapshot)

        buttons_row.addStretch()
        buttons_row.addWidget(self.btn_refresh)
        buttons_row.addWidget(self.btn_create)

        # ── Verificar Sync — botão flutuante (FAB), canto inferior direito ──
        # (mesmo padrão do Clonezilla: círculo, ícone, sombra, reposicionado
        # no resizeEvent). Nome do atributo mantido (self.btn_verify) pra não
        # quebrar set_busy()/outras referências existentes.
        self.btn_verify = QPushButton(self)
        self.btn_verify.setIcon(qta.icon(VERIFY_GLYPH, color="#0a0b0f"))
        self.btn_verify.setIconSize(QSize(24, 24))
        self.btn_verify.setFixedSize(56, 56)
        self.btn_verify.setCursor(Qt.PointingHandCursor)
        self.btn_verify.setToolTip(tr("snapshots.fab_verify_tooltip"))
        self.btn_verify.setStyleSheet("""
            QPushButton {
                background: #9bf0bd;
                border: none;
                border-radius: 28px;
            }
            QPushButton:hover {
                background: rgba(155, 240, 189, 220);
            }
            QPushButton:disabled {
                background: rgba(155, 240, 189, 90);
            }
            QPushButton:focus {
                outline: none;
            }
            QToolTip {
                background: #14151c;
                color: #e4e7ec;
                border: 1px solid rgba(155, 240, 189, 140);
                padding: 4px 8px;
                border-radius: 6px;
            }
        """)
        verify_shadow = QGraphicsDropShadowEffect(self.btn_verify)
        verify_shadow.setBlurRadius(24)
        verify_shadow.setOffset(0, 4)
        verify_shadow.setColor(QColor(0, 0, 0, 160))
        self.btn_verify.setGraphicsEffect(verify_shadow)
        self.btn_verify.clicked.connect(self.verify_all_snapshots)
        self.btn_verify.raise_()

        # coluna direita: label + card bordado alinhados com esquerda
        right_column = QVBoxLayout()
        right_column.setSpacing(0)
        right_column.setContentsMargins(0, 0, 0, 0)

        right_column.addWidget(self.right_frame)
        right_column.addSpacing(24)
        right_column.addLayout(buttons_row)

        control_layout.addLayout(left_panel, 5)
        control_layout.addLayout(right_column, 4)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(14)
        self.scroll_layout.addStretch(1)

        self.scroll.setWidget(self.scroll_content)
        sep_line = QFrame()
        sep_line.setFixedHeight(1)
        sep_line.setStyleSheet("background: rgba(255,255,255,6); border: none;")

        root.addWidget(self.control_card)
        root.addWidget(sep_line)
        root.addWidget(self.scroll, 1)

        # ── Toast dos tooltips de RESTORE/SYNC/DELETE (canto superior
        # direito, igual ao operation_status_row do eggs_page.py) ──
        # É um QFrame filho DESTA página (não uma janela topo-nível como
        # a primeira tentativa) — o compositor/mutter custom do Apollo não
        # renderizava certo a transparência/cantos de uma janela Qt.ToolTip
        # própria, então voltamos pro mesmo padrão que já funciona no Eggs.
        # Sem spinner (removido por pedido — é só um texto, não uma
        # operação em andamento).
        self._button_toast = QFrame(self)
        self._toast_target: QWidget | None = None
        self._button_toast.setObjectName("ButtonToast")
        self._button_toast.setStyleSheet(
            """
            QFrame#ButtonToast {
                background: rgba(15, 18, 28, 235);
                border: 1px solid rgba(35, 166, 255, 110);
                border-radius: 12px;
            }
            """
        )
        toast_layout = QHBoxLayout(self._button_toast)
        toast_layout.setContentsMargins(18, 12, 18, 12)

        self._toast_label = QLabel("")
        self._toast_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        self._toast_label.setStyleSheet("color: #ecf4ff; background: transparent;")

        toast_layout.addWidget(self._toast_label)
        self._button_toast.hide()
        self._button_toast.adjustSize()

        # Timer próprio de esconder — nada de QToolTip.showText/cache.
        self._toast_hide_timer = QTimer(self)
        self._toast_hide_timer.setSingleShot(True)
        self._toast_hide_timer.setInterval(8000)
        self._toast_hide_timer.timeout.connect(self._hide_button_toast)

        self.refresh_destinations()
        self.set_scope("both")
        self._position_verify_fab()
        self.btn_verify.raise_()

        # ── Troca de idioma em tempo real, sem precisar reiniciar o app ──
        i18n.language_changed.connect(self._retranslate)

    def _retranslate(self) -> None:
        self.lbl_destination.setText(tr("snapshots.destination_label"))
        self.lbl_scope.setText(tr("snapshots.scope_label"))
        scope_texts = {
            "root": (tr("snapshots.scope_root_title"), tr("snapshots.scope_root_subtitle")),
            "home": (tr("snapshots.scope_home_title"), tr("snapshots.scope_home_subtitle")),
            "both": (tr("snapshots.scope_both_title"), tr("snapshots.scope_both_subtitle")),
        }
        for key, card in self.scope_cards.items():
            title, subtitle = scope_texts.get(key, ("", ""))
            card.set_text(title, subtitle)
        self.btn_refresh.setText(tr("snapshots.btn_refresh_space"))
        self.btn_create.setText(tr("snapshots.btn_create_snapshot"))
        self.btn_verify.setToolTip(tr("snapshots.fab_verify_tooltip"))
        # Combo de destino e resumo à direita são reconstruídos com o
        # idioma novo; a lista de snapshots (cards/empty state) também é
        # recriada do zero, então pega o idioma novo automaticamente.
        self.refresh_destinations()

    def _reposition_button_toast(self) -> None:
        """Posicionado logo ABAIXO do botão que disparou o hover (com uma
        folga de 8px pra não ficar colado/por cima), centralizado
        horizontalmente em relação a ele — em vez de um ponto fixo da
        página. Precisa do widget-alvo guardado em `_toast_target` porque
        é chamado de novo em resizeEvent, sem o evento de hover original."""
        if self._toast_target is None:
            return
        self._button_toast.adjustSize()
        gap = 20
        target = self._toast_target
        target_top_left_global = target.mapToGlobal(QPoint(0, target.height()))
        center_x_global = target.mapToGlobal(QPoint(target.width() // 2, 0)).x()

        toast_w = self._button_toast.width()
        x_global = center_x_global - toast_w // 2
        y_global = target_top_left_global.y() + gap

        local = self.mapFromGlobal(QPoint(x_global, y_global))
        # Não deixa vazar pra fora da página horizontalmente.
        x = min(max(4, local.x()), self.width() - toast_w - 4)
        self._button_toast.move(x, local.y())
        self._button_toast.raise_()

    def _show_button_toast(self, target: QWidget, text: str) -> None:
        self._toast_target = target
        self._toast_label.setText(text)
        self._button_toast.show()
        self._reposition_button_toast()
        self._toast_hide_timer.start()

    def _hide_button_toast(self) -> None:
        self._toast_hide_timer.stop()
        self._button_toast.hide()
        self._toast_target = None

    def showEvent(self, event) -> None:
        """A página é criada uma vez só (QStackedWidget) — sem isso, a
        lista de destinos só era montada na primeira vez e nunca mais
        atualizava sozinha, mesmo que outro disco fosse montado depois
        (ex: via o botão 'Montar discos do sistema' na página Disks).
        Também reposiciona o FAB aqui: no __init__ a página ainda não
        tem o tamanho final dentro do QStackedWidget, então
        self.width()/height() ali podem estar errados."""
        super().showEvent(event)
        self.refresh_destinations()
        self._position_verify_fab()
        self.btn_verify.raise_()

    def set_scope(self, scope: str):
        if scope not in {"root", "home", "both"}:
            return
        self.scope = scope
        for key, card in self.scope_cards.items():
            card.set_active(key == scope)

    def current_scope(self) -> str:
        return self.scope if self.scope in {"root", "home", "both"} else "both"

    def current_destination(self) -> StorageDestination | None:
        return self.cmb_destination.currentData()

    def _format_combo_item(self, dest: StorageDestination) -> str:
        return tr("snapshots.combo_item").format(
            label=dest.label, free=format_gb(dest.free_gb),
            mountpoint=dest.mountpoint, fs_type=dest.fs_type,
        )

    def refresh_destinations(self):
        current_mount = None
        current = self.current_destination()
        if current is not None:
            current_mount = current.mountpoint

        self.destinations = list_backup_destinations()

        self.cmb_destination.blockSignals(True)
        self.cmb_destination.clear()

        for dest in self.destinations:
            self.cmb_destination.addItem(self._format_combo_item(dest), dest)

        self.cmb_destination.blockSignals(False)

        if not self.destinations:
            self.lbl_destination_info.setText(tr("snapshots.no_destinations_found"))
            self.lbl_destination_meta.setText(tr("snapshots.mount_a_disk"))
            self.lbl_space_percent.setText("—")
            self.space_fill.setGeometry(0, 0, 0, 5)
            self.btn_create.setEnabled(False)
            self.btn_verify.setEnabled(False)
            self.rebuild_snapshot_view()
            return

        self.btn_create.setEnabled(True)
        self.btn_verify.setEnabled(True)

        if current_mount:
            idx = next(
                (i for i, d in enumerate(self.destinations) if d.mountpoint == current_mount),
                0,
            )
            self.cmb_destination.setCurrentIndex(idx)
        else:
            self.cmb_destination.setCurrentIndex(0)

        self.update_destination_summary()
        self.rebuild_snapshot_view()

    def _on_destination_changed(self, index: int):
        if index < 0:
            self.lbl_space_percent.setText("—")
            return
        self.update_destination_summary()

    def _on_destination_activated(self, index: int):
        if index < 0:
            return
        self.update_destination_summary()
        self.rebuild_snapshot_view()

    def update_destination_summary(self):
        dest = self.current_destination()
        if dest is None:
            self.lbl_destination_info.setText(tr("snapshots.select_destination"))
            self.lbl_destination_meta.setText("—")
            self.lbl_space_percent.setText("—")
            self.space_fill.setGeometry(0, 0, 0, 5)
            return

        used_pct = 0
        if dest.total_bytes > 0:
            used_pct = int(round((dest.used_bytes / dest.total_bytes) * 100))

        free_pct = max(0, 100 - used_pct)
        fill_width = max(0, int(self.space_bar.width() * used_pct / 100))
        self.space_fill.setGeometry(0, 0, fill_width, 5)

        self.lbl_destination_info.setText(dest.label)
        self.lbl_destination_meta.setText(
            tr("snapshots.free_of_total").format(
                free=format_gb(dest.free_gb), total=format_gb(dest.total_gb),
                mountpoint=dest.mountpoint, fs_type=dest.fs_type,
            )
        )
        self.lbl_space_percent.setText(tr("snapshots.free_percent").format(pct=free_pct))

    def _position_verify_fab(self) -> None:
        margin = 28
        self.btn_verify.move(
            self.width() - self.btn_verify.width() - margin,
            self.height() - self.btn_verify.height() - margin,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_destination_summary()
        if self._button_toast.isVisible():
            self._reposition_button_toast()
        self._position_verify_fab()
        self.btn_verify.raise_()

    def current_backup_root(self) -> Path | None:
        dest = self.current_destination()
        if dest is None:
            return None
        return Path(dest.backup_root)

    def set_busy(self, busy: bool):
        self.cmb_destination.setEnabled(not busy)
        self.btn_refresh.setEnabled(not busy)
        self.btn_verify.setEnabled(not busy)
        self.btn_create.setEnabled(not busy)
        self.scroll.setEnabled(not busy)
        for card in self.scope_cards.values():
            card.setEnabled(not busy)
        # Trava a janela principal inteira (não só os controles dessa
        # página) enquanto o processo elevado (pkexec) roda em segundo
        # plano — inclui o diálogo "Verificando Snapshot Irmão", que roda
        # num processo do SO separado e por isso não consegue travar o
        # Carbonara principal sozinho via modalidade do Qt (modalidade só
        # funciona dentro do mesmo processo/QApplication).
        window = self.window()
        if window is not None:
            window.setEnabled(not busy)

    def rebuild_snapshot_view(self):
        clear_layout(self.scroll_layout)

        backup_root = self.current_backup_root()
        if backup_root is None:
            self.scroll_layout.addStretch(1)
            return

        entries = collect_snapshots(backup_root)

        if not entries:
            empty = QFrame()
            empty.setObjectName("EmptyState")
            empty.setStyleSheet(
                """
                QFrame#EmptyState {
                    border: 1px solid rgba(31, 92, 255, 55);
                    border-radius: 16px;
                    background: rgba(8, 12, 20, 120);
                }
                QFrame#EmptyState QLabel {
                    border: none;
                    background: transparent;
                }
                """
            )
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(32, 36, 32, 36)
            empty_layout.setSpacing(4)
            empty_layout.setAlignment(Qt.AlignCenter)

            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setFixedSize(48, 48)
            icon_label.setPixmap(qta.icon(SNAPSHOT_GLYPH, color="#3a6a9a").pixmap(28, 28))
            icon_label.setStyleSheet(
                "background: rgba(35, 166, 255, 18); border-radius: 14px;"
            )

            icon_row = QHBoxLayout()
            icon_row.addStretch()
            icon_row.addWidget(icon_label)
            icon_row.addStretch()
            empty_layout.addLayout(icon_row)
            empty_layout.addSpacing(14)

            title = QLabel(tr("snapshots.empty_title"))
            title.setAlignment(Qt.AlignCenter)
            title.setStyleSheet("color: #ecf4ff;")
            title.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
            empty_layout.addWidget(title)

            label = QLabel(tr("snapshots.empty_subtitle"))
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #9aa6b2;")
            label.setFont(QFont("DejaVu Sans Mono", 9))
            empty_layout.addWidget(label)

            self.scroll_layout.addWidget(empty)
            self.scroll_layout.addStretch(1)
            return

        grouped = defaultdict(list)
        for entry in entries:
            grouped[entry.kind.upper()].append(entry)

        # Lookup para encontrar o snapshot irmão (mesmo stamp, kind oposto)
        by_key = {(e.kind.upper(), e.path.name): e for e in entries}

        def _sibling_of(e: SnapshotEntry) -> "SnapshotEntry | None":
            kind = e.kind.upper()
            sib_kind = "HOME" if kind == "ROOT" else "ROOT" if kind == "HOME" else None
            return by_key.get((sib_kind, e.path.name)) if sib_kind else None

        ordered_kinds = []
        for preferred in ("ROOT", "HOME"):
            if preferred in grouped:
                ordered_kinds.append(preferred)

        for kind in sorted(grouped.keys()):
            if kind not in ordered_kinds:
                ordered_kinds.append(kind)

        SECTION_ACCENTS = {"ROOT": "#23a6ff", "HOME": "#e0a840"}

        for kind in ordered_kinds:
            section_icon = ROOT_GLYPH if kind == "ROOT" else HOME_GLYPH if kind == "HOME" else SNAPSHOT_GLYPH
            accent_color = SECTION_ACCENTS.get(kind, "#7d8a99")
            section = SectionCard(
                kind,
                str(backup_root / kind),
                section_icon,
                accent_color=accent_color,
            )
            for entry in grouped[kind]:
                card = SnapshotCard(entry, sibling=_sibling_of(entry), page=self)
                card.btn_restore.clicked.connect(
                    lambda _, e=entry: self.restore_snapshot(e)
                )
                card.btn_sync.clicked.connect(
                    lambda _, e=entry: self.sync_snapshot(e)
                )
                card.btn_delete.clicked.connect(
                    lambda _, e=entry: self.delete_snapshot(e)
                )
                # Grade de 2 colunas DENTRO da seção — não é ROOT e HOME
                # lado a lado, é cada seção ocupando a largura toda, com
                # os próprios snapshots dela preenchendo pelo menos 2
                # por linha conforme mais forem criados.
                section.add_card(card)

            self.scroll_layout.addWidget(section)
            # Respiro extra entre grupos (ROOT vs HOME) — maior que o
            # espaçamento padrão do scroll_layout entre cards do mesmo
            # grupo, pra reforçar visualmente onde um grupo termina.
            self.scroll_layout.addSpacing(18)

        self.scroll_layout.addStretch(1)

    def refresh_list(self):
        # refresh_destinations relê o disco (bytes livres/usados) e chama
        # rebuild_snapshot_view internamente — garante que o espaço livre
        # exibido no RightPanel reflita o estado real após o backup.
        self.refresh_destinations()

    def create_snapshot(self):
        dest = self.current_destination()
        if dest is None:
            QMessageBox.warning(self, "Carbonara", tr("snapshots.select_destination_first"))
            return

        if OperationManager.is_running():
            current = OperationManager.current()
            QMessageBox.warning(
                self,
                "Carbonara",
                tr("snapshots.op_already_running").format(name=current.name if current else 'busy'),
            )
            return

        confirm_dialog = _CreateSnapshotConfirmDialog(self.current_scope(), parent=self)
        if confirm_dialog.exec() != QDialog.Accepted:
            return

        if not OperationManager.start(
            "backup",
            f"Snapshot on {dest.label} ({dest.mountpoint})",
        ):
            QMessageBox.warning(
                self,
                "Carbonara",
                tr("snapshots.op_exclusive_running"),
            )
            return

        self.set_busy(True)
        self._current_op_kind = "backup"
        self._sync_entry = None

        import json

        args_json = json.dumps({
            "destination_mountpoint": dest.mountpoint,
            "scope": self.current_scope(),
        })

        cmd = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "backup.create_backup",
            args_json,
        ]

        try:
            self._backup_proc = subprocess.Popen(cmd)
            self._poll_timer.start()
        except Exception as e:
            OperationManager.finish()
            self.set_busy(False)
            _show_error("Carbonara Backup", str(e), parent=self)

    def _poll_backup_process(self):
        if self._backup_proc is None:
            return

        rc = self._backup_proc.poll()
        if rc is None:
            return

        self._poll_timer.stop()
        self._backup_proc = None
        OperationManager.finish()
        self.set_busy(False)

        # ── PATCH 2: sempre atualiza a lista, depois decide se mostra aviso ──
        self.refresh_list()

        # rc=0   → sucesso silencioso
        # rc=2   → cancelamento intencional pelo usuário (BackupProgressDialog.done(2))
        # rc=126 → pkexec cancelado pelo usuário (ESC ou Cancelar na autenticação)
        # rc<0   → processo terminado por sinal (ex: -6/SIGABRT, -9/SIGKILL),
        #          o que ocorre normalmente ao cancelar/matar o subprocesso
        #          durante um backup em andamento — não é um erro real.
        # rc=outro → erro real
        if rc not in (0, 2, 126) and rc >= 0:
            _show_error(
                "Carbonara Backup",
                tr("snapshots.backup_exit_code").format(rc=rc),
                parent=self,
            )

        # Após um SYNC concluído com sucesso, oferece sincronizar o
        # snapshot irmão (ROOT/HOME com o mesmo stamp), se existir.
        if (
            rc == 0
            and self._current_op_kind == "sync"
            and self._sync_entry is not None
            and self._offer_pair_after_sync
        ):
            self._maybe_offer_pair_sync(self._sync_entry)

        # Após o botão VERIFICAR checar ROOT e HOME de verdade, oferece
        # sincronizar cada um que estiver realmente desatualizado.
        if rc == 0 and self._current_op_kind == "verify":
            self._handle_verify_result()

        # Se o usuário marcou mais de um no dialog combinado (ex: "Sincronizar
        # ambas"), encadeia o próximo da fila automaticamente — já foi
        # confirmado, não precisa perguntar de novo.
        if rc == 0 and self._current_op_kind == "sync" and self._sync_queue:
            next_entry = self._sync_queue.pop(0)
            # Garantia defensiva: nesse ponto o finish() já rodou linhas
            # acima, mas forçamos de novo antes de encadear — nada mais
            # deveria estar "rodando" aqui, então isso é seguro e evita
            # qualquer resquício de estado impedir o próximo da fila.
            OperationManager.finish()
            self._start_sync_process(next_entry, offer_pair=False)
            return

        self._sync_entry = None
        self._current_op_kind = None
        self._verify_entries = {}
        self._sync_queue = []

    def restore_snapshot(self, entry: SnapshotEntry):
        if OperationManager.is_running():
            QMessageBox.warning(
                self, "Carbonara", tr("snapshots.op_exclusive_running")
            )
            return

        dialog = _RestoreDialog(entry, parent=self)
        dialog.exec()

    def sync_snapshot(self, entry: SnapshotEntry):
        if OperationManager.is_running():
            QMessageBox.warning(
                self, "Carbonara", "Another exclusive operation is already running."
            )
            return

        dialog = _SyncConfirmDialog(entry, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        self._start_sync_process(entry, offer_pair=True)

    def _start_sync_process(self, entry: SnapshotEntry, offer_pair: bool = True):
        if not OperationManager.start("sync", f"Sync snapshot {entry.path.name}"):
            QMessageBox.warning(self, "Carbonara", "Another operation is already running.")
            return

        self.set_busy(True)
        self._current_op_kind = "sync"
        self._sync_entry = entry
        self._offer_pair_after_sync = offer_pair

        # Arquivo onde o processo elevado (pkexec) grava o resultado real
        # da checagem de pendências do snapshot irmão — evita um segundo
        # prompt de autenticação e evita heurísticas por horário.
        pair_check_path = Path(f"/tmp/carbonara-pair-check-{os.getpid()}-{entry.path.name}.json")
        self._pair_check_path = pair_check_path

        import json

        args_json = json.dumps({
            "snapshot_path": str(entry.path),
            "offer_pair": offer_pair,
            "pair_check_path": str(pair_check_path),
        })

        cmd = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "backup.sync_snapshot",
            args_json,
        ]

        try:
            self._backup_proc = subprocess.Popen(cmd)
            self._poll_timer.start()
        except Exception as e:
            OperationManager.finish()
            self.set_busy(False)
            _show_error("Carbonara Sync", str(e), parent=self)

    def _maybe_offer_pair_sync(self, entry: SnapshotEntry) -> None:
        """Lê o resultado do rsync --dry-run gravado pelo processo elevado
        e só pergunta se houver mudanças pendentes reais no snapshot irmão."""
        pair_check_path = getattr(self, "_pair_check_path", None)
        if pair_check_path is None:
            return
        if not pair_check_path.exists():
            _show_error(
                "Verificação de snapshot irmão",
                "A checagem não gerou resultado — o arquivo temporário não "
                "foi criado. Verifique se ui/widgets/backup_progress.py está "
                "atualizado no projeto (classe PairCheckProgressDialog).",
                parent=self,
            )
            return

        try:
            payload = json.loads(pair_check_path.read_text(encoding="utf-8"))
        finally:
            try:
                pair_check_path.unlink()
            except OSError:
                pass

        if payload.get("error"):
            _show_error(
                "Verificação de snapshot irmão",
                f"A checagem falhou (sync já concluído normalmente):\n\n{payload['error']}",
                parent=self,
            )
            return

        if not payload.get("needs_sync"):
            return

        sibling_kind = payload.get("sibling_kind")
        sibling_path = payload.get("sibling_path")
        if not sibling_kind or not sibling_path:
            return

        backup_root = entry.path.parent.parent
        sibling_entry = next(
            (
                e for e in collect_snapshots(backup_root)
                if e.kind.upper() == sibling_kind and str(e.path) == sibling_path
            ),
            None,
        )
        if sibling_entry is None:
            return

        dlg = _OfferPairSyncDialog(sibling_kind, sibling_entry.path.name, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        # Garantia defensiva — ver comentário equivalente no encadeamento
        # da fila em _poll_backup_process.
        OperationManager.finish()
        self._start_sync_process(sibling_entry, offer_pair=False)

    def verify_all_snapshots(self):
        """Botão VERIFICAR: roda uma única sessão pkexec que faz
        rsync --dry-run real do ROOT e do HOME mais recentes contra o
        sistema atual, e oferece sincronizar cada um que estiver
        realmente desatualizado — sem depender de heurística de data."""
        if OperationManager.is_running():
            QMessageBox.warning(
                self, "Carbonara", "Another exclusive operation is already running."
            )
            return

        dest = self.current_destination()
        if dest is None:
            return

        backup_root = Path(dest.backup_root)
        all_entries = [
            e for e in collect_snapshots(backup_root) if e.kind.upper() in ("ROOT", "HOME")
        ]

        if not all_entries:
            _show_info(
                "Carbonara",
                "Nenhum snapshot ROOT/HOME encontrado para verificar.",
                parent=self,
            )
            return

        # Por padrão, pré-marca só o mais recente de cada tipo (mesmo
        # comportamento de antes) — o usuário pode marcar outros também.
        latest_by_kind: dict[str, SnapshotEntry] = {}
        for e in all_entries:
            k = e.kind.upper()
            if k not in latest_by_kind or e.path.name > latest_by_kind[k].path.name:
                latest_by_kind[k] = e
        default_checked = {_VerifySelectDialog.make_id(e) for e in latest_by_kind.values()}

        if len(all_entries) == 1:
            # Só existe um candidato — nada para escolher, verifica direto.
            selected = all_entries
        else:
            select_dlg = _VerifySelectDialog(all_entries, default_checked=default_checked, parent=self)
            if select_dlg.exec() != QDialog.Accepted:
                return

            selected = select_dlg.selected_entries()
            if not selected:
                return

        verify_label_op = ", ".join(f"{e.kind.upper()} {e.path.name}" for e in selected)
        if not OperationManager.start("verify", f"Verificando {verify_label_op}"):
            QMessageBox.warning(self, "Carbonara", "Another operation is already running.")
            return

        self.set_busy(True)
        self._current_op_kind = "verify"
        self._verify_entries = {_VerifySelectDialog.make_id(e): e for e in selected}

        verify_path = Path(f"/tmp/carbonara-verify-{os.getpid()}.json")
        self._verify_check_path = verify_path

        targets = {
            _VerifySelectDialog.make_id(e): {"kind": e.kind.upper(), "path": str(e.path)}
            for e in selected
        }
        kinds_involved = sorted({e.kind.upper() for e in selected})
        verify_label = (
            " + ".join(kinds_involved) if len(selected) <= 2
            else f"{len(selected)} snapshots"
        )

        args_json = json.dumps({
            "targets": targets,
            "label": verify_label,
            "result_path": str(verify_path),
        })

        cmd = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "backup.verify",
            args_json,
        ]

        try:
            self._backup_proc = subprocess.Popen(cmd)
            self._poll_timer.start()
        except Exception as e:
            OperationManager.finish()
            self.set_busy(False)
            _show_error("Carbonara Verify", str(e), parent=self)

    def _handle_verify_result(self) -> None:
        """Lê o resultado real do VERIFICAR e oferece sincronizar, em
        sequência, cada snapshot (ROOT e/ou HOME) que estiver desatualizado."""
        verify_path = getattr(self, "_verify_check_path", None)
        if verify_path is None:
            return
        if not verify_path.exists():
            _show_error(
                "Carbonara Verify",
                "A verificação não gerou resultado — o arquivo temporário "
                "não foi criado.",
                parent=self,
            )
            return

        try:
            payload = json.loads(verify_path.read_text(encoding="utf-8"))
        finally:
            try:
                verify_path.unlink()
            except OSError:
                pass

        entries = getattr(self, "_verify_entries", {}) or {}

        error_ids = [
            id_ for id_, info in payload.items()
            if isinstance(info, dict) and info.get("status") == "error" and id_ in entries
        ]
        stale_ids = [
            id_ for id_, info in payload.items()
            if isinstance(info, dict) and info.get("status") == "stale" and id_ in entries
        ]

        def _label(id_: str) -> str:
            e = entries[id_]
            return f"{e.kind.upper()} {e.path.name}"

        # Qualquer snapshot que não pôde ser verificado (erro real, não "sem
        # mudanças") é reportado explicitamente — nunca tratado como "em dia"
        # por padrão, pra não mascarar uma falha real como sucesso.
        if error_ids:
            details = "\n".join(
                f"{_label(id_)}: {payload[id_].get('detail', 'motivo desconhecido')}"
                for id_ in error_ids
            )
            _show_error(
                "Carbonara Verify",
                f"Não foi possível verificar {', '.join(_label(i) for i in error_ids)} de verdade:\n\n{details}",
                parent=self,
            )
            if not stale_ids:
                return

        if not stale_ids:
            lines = [
                f"Snapshot {e.path.name} {e.kind.upper()} já está sincronizado com o estado atual do sistema."
                for id_, e in sorted(entries.items())
            ]
            _show_info(
                "Carbonara",
                "\n".join(lines) if lines else "Nenhum snapshot verificado.",
                parent=self,
            )
            return

        stale_list = [(entries[id_].kind.upper(), entries[id_].path.name) for id_ in stale_ids]
        dlg = _VerifyResultsDialog(stale_list, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        selected_labels = dlg.selected_kinds()
        if not selected_labels:
            return

        # _VerifyResultsDialog trabalha com (kind, name) — remonta pra id_
        # composto pra buscar o SnapshotEntry certo de volta.
        selected_ids = [
            id_ for id_ in stale_ids
            if f"{entries[id_].kind.upper()}|{entries[id_].path.name}" in selected_labels
        ]

        # Sync é uma operação exclusiva — enfileira e processa uma de cada
        # vez, encadeando automaticamente (sem perguntar de novo, já que
        # o usuário acabou de confirmar todos no mesmo dialog).
        queue = [entries[id_] for id_ in selected_ids]
        if not queue:
            return
        first = queue.pop(0)
        self._sync_queue = queue
        # Garantia defensiva — ver comentário equivalente no encadeamento
        # da fila em _poll_backup_process.
        OperationManager.finish()
        self._start_sync_process(first, offer_pair=False)

    def delete_snapshot(self, entry: SnapshotEntry):
        if OperationManager.is_running():
            QMessageBox.warning(
                self,
                "Carbonara",
                tr("snapshots.op_exclusive_running"),
            )
            return

        # Se este for o último snapshot ROOT, apagá-lo também remove o
        # carbonara-restore.sh (nada sobra pra restaurar) — avisa antes.
        is_last_root = False
        if entry.kind.upper() == "ROOT":
            dest = self.current_destination()
            if dest is not None:
                root_count = sum(
                    1 for e in collect_snapshots(Path(dest.backup_root))
                    if e.kind.upper() == "ROOT"
                )
                is_last_root = root_count <= 1

        dialog = _DeleteConfirmDialog(entry, is_last_root=is_last_root, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        if not OperationManager.start("delete", f"Delete snapshot {entry.path.name}"):
            QMessageBox.warning(self, "Carbonara", tr("snapshots.op_exclusive_running"))
            return

        self.set_busy(True)

        # Dialog de progresso — aparece enquanto o worker roda
        self._delete_progress = _DeleteProgressDialog(entry.path.name, parent=self)
        self._delete_progress.show()

        worker = _DeleteWorker(entry.path, parent=self)
        worker.finished_ok.connect(lambda msg: self._on_delete_ok(msg))
        worker.failed.connect(lambda msg: self._on_delete_fail(msg))
        worker.start()
        self._delete_worker = worker

    def _on_delete_ok(self, msg: str) -> None:
        self._delete_progress.close()
        OperationManager.finish()
        self.set_busy(False)
        self.refresh_list()

    def _on_delete_fail(self, msg: str) -> None:
        self._delete_progress.close()
        OperationManager.finish()
        self.set_busy(False)
        _show_error("Delete Snapshot", tr("snapshots.delete_failed_message").format(msg=msg), parent=self)
        self.refresh_list()


# ── Shared styled dialogs ─────────────────────────────────────────────────────

class _ErrorDialog(QDialog):
    """Substitui QMessageBox.critical com identidade visual Carbonara."""

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
        icon.setPixmap(qta.icon("mdi6.alert-circle", color="#ff6666").pixmap(16, 16))
        icon.setStyleSheet("QLabel { background: rgba(200,60,60,40); border-radius: 7px; }")

        lbl = QLabel(title)
        lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.setFixedSize(24, 24)
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
                background: rgba(30, 10, 10, 255);
                border-bottom: 1px solid rgba(200, 60, 60, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#ErrBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#ErrClose {
                background: transparent; border: none;
                color: #4a5a6a; font-size: 11px; border-radius: 5px;
            }
            QPushButton#ErrClose:hover {
                background: rgba(200,60,60,60); color: #ff8888;
            }
            QPushButton#ErrBtnOk {
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(31, 92, 255, 120);
                border-radius: 8px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px; padding: 5px 0;
            }
            QPushButton#ErrBtnOk:hover {
                background: rgba(23, 147, 209, 70);
                border-color: rgba(35, 166, 255, 180);
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


class _InfoDialog(QDialog):
    """Variante verde do _ErrorDialog, para mensagens neutras/positivas
    (ex: 'já está tudo em dia') — mesma identidade visual, sem o
    QMessageBox genérico do sistema."""

    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMaximumWidth(680)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(title, message)
        self._apply_styles()
        self.adjustSize()

    def _build_ui(self, title: str, message: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("InfoHeader")
        header.setFixedHeight(46)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 14, 0)

        icon = QLabel()
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.check-circle", color="#9bf0bd").pixmap(16, 16))
        icon.setStyleSheet("QLabel { background: rgba(74,222,128,40); border-radius: 7px; }")

        lbl = QLabel(title)
        lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.setFixedSize(24, 24)
        btn_x.mousePressEvent = lambda e: self.accept()

        h_layout.addWidget(icon)
        h_layout.addSpacing(8)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        body = QFrame()
        body.setObjectName("InfoBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 24, 24, 22)
        b_layout.setSpacing(20)

        msg = QLabel(message.replace("\n", "<br><br>"))
        msg.setTextFormat(Qt.RichText)
        msg.setFont(QFont("DejaVu Sans Mono", 10))
        msg.setStyleSheet("color: #c8d4e0;")
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse)

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("InfoBtnOk")
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
            QFrame#InfoHeader {
                background: rgba(10, 30, 16, 255);
                border-bottom: 1px solid rgba(74, 222, 128, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#InfoBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#InfoBtnOk {
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(74, 222, 128, 120);
                border-radius: 8px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px; padding: 5px 0;
            }
            QPushButton#InfoBtnOk:hover {
                background: rgba(74, 222, 128, 40);
                border-color: rgba(94, 234, 149, 200);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


def _show_info(title: str, message: str, parent=None) -> None:
    _InfoDialog(title, message, parent=parent).exec()


# ── Restore helpers ───────────────────────────────────────────────────────────

class _MaxLabel(QLabel):
    """Botão maximizar/restaurar com hover real."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self._set_normal()

    def _set_normal(self):
        self.setStyleSheet(
            "QLabel { color: #c8d4e0; font-size: 14px; "
            "border-radius: 6px; background: transparent; }"
        )
        self.setText("□")

    def _set_hover(self):
        self.setStyleSheet(
            "QLabel { color: #23a6ff; font-size: 14px; "
            "border-radius: 6px; background: rgba(35,166,255,30); }"
        )

    def enterEvent(self, event):
        self._set_hover()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_normal()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            win = self.window()
            if getattr(win, "_is_maximized", False):
                win.resize(win._normal_size)
                win.move(win._normal_pos)
                win._is_maximized = False
                self.setText("□")
            else:
                from PySide6.QtWidgets import QApplication
                win._normal_size = win.size()
                win._normal_pos = win.pos()
                screen = QApplication.primaryScreen().availableGeometry()
                win.resize(screen.width() - 40, screen.height() - 40)
                win.move(20, 20)
                win._is_maximized = True
                self.setText("❐")
        super().mousePressEvent(event)


class _CloseLabel(QLabel):
    """Label ✕ com hover real — QLabel:hover não funciona sem WA_Hover."""
    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setFixedSize(28, 28)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self._set_normal()

    def _set_normal(self):
        self.setStyleSheet(
            "QLabel { color: #c8d4e0; font-size: 14px; "
            "border-radius: 6px; background: transparent; }"
        )

    def _set_hover(self):
        self.setStyleSheet(
            "QLabel { color: #ff8888; font-size: 14px; "
            "border-radius: 6px; background: rgba(200,60,60,80); }"
        )

    def enterEvent(self, event):
        self._set_hover()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_normal()
        super().leaveEvent(event)


class _NavLabel(QLabel):
    """Botão de navegação (←) com hover real."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self._pixmap_normal = qta.icon("mdi6.arrow-left", color="#c8d4e0").pixmap(16, 16)
        self._pixmap_hover = qta.icon("mdi6.arrow-left", color="#23a6ff").pixmap(16, 16)
        self._set_normal()

    def _set_normal(self):
        self.setPixmap(self._pixmap_normal)
        self.setStyleSheet(
            "QLabel { background: rgba(10,15,25,200); border-radius: 6px; "
            "border: 1px solid rgba(31,92,255,80); }"
        )

    def _set_hover(self):
        self.setPixmap(self._pixmap_hover)
        self.setStyleSheet(
            "QLabel { background: rgba(23,147,209,70); border-radius: 6px; "
            "border: 1px solid rgba(35,166,255,180); }"
        )

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        if enabled:
            self._set_normal()
        else:
            self.setPixmap(qta.icon("mdi6.arrow-left", color="#3a4a5a").pixmap(16, 16))
            self.setStyleSheet(
                "QLabel { background: rgba(10,15,25,100); border-radius: 6px; "
                "border: 1px solid rgba(31,92,255,30); }"
            )

    def enterEvent(self, event):
        if self.isEnabled():
            self._set_hover()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.isEnabled():
            self._set_normal()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mousePressEvent(event)


class _RestoreDialog(QDialog):
    """Dialog de restore com 3 opções."""

    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(tr("snapshots.restore_dialog_title"))
        self.setModal(True)
        extra_height = 92 if entry.path.parent.name.upper() == "HOME" else 0
        self.setFixedSize(880, 514 + extra_height)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("RstHeader")
        header.setFixedHeight(60)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 18, 0)
        h_layout.setSpacing(6)

        icon = QLabel()
        icon.setFixedSize(50, 50)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.file-restore-outline", color="#8fd4ff").pixmap(40, 40))
        icon.setStyleSheet("QLabel { background: transparent; }")

        lbl = QLabel(tr("snapshots.restore_dialog_title"))
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ffffff; background: transparent;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()

        h_layout.addWidget(icon)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        body = QFrame()
        body.setObjectName("RstBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 20, 28, 22)
        b_layout.setSpacing(10)
        # Snapshot info — réplica completa do SnapshotCard (título, meta+size, last sync)
        snap_row = QHBoxLayout()
        snap_row.setSpacing(14)
        snap_row.setContentsMargins(0, 0, 0, 0)

        snap_icon = icon_badge(SNAPSHOT_GLYPH, 38)

        snap_text = QVBoxLayout()
        snap_text.setSpacing(4)
        snap_text.setContentsMargins(0, 0, 0, 0)

        snap_title = QLabel(self.entry.path.name)
        snap_title_font = QFont("DejaVu Sans Mono")
        snap_title_font.setPointSizeF(10.5)
        snap_title_font.setBold(True)
        snap_title.setFont(snap_title_font)
        snap_title.setStyleSheet("color: #ecf4ff;")

        snap_meta_row = QHBoxLayout()
        snap_meta_row.setSpacing(8)
        snap_meta_row.setContentsMargins(0, 0, 0, 0)

        snap_meta = QLabel(self.entry.meta_text)
        snap_meta.setFont(QFont("DejaVu Sans Mono", 10))
        snap_meta.setStyleSheet("color: #6b7a8d;")
        snap_meta_row.addWidget(snap_meta)

        if self.entry.size_str:
            snap_size_prefix = QLabel(tr("snapshots.size_label"))
            snap_size_prefix.setFont(QFont("DejaVu Sans Mono", 9))
            snap_size_prefix.setStyleSheet("color: #6b7a8d;")
            snap_meta_row.addWidget(snap_size_prefix)

            snap_size_val = QLabel(self.entry.size_str)
            snap_size_val.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
            snap_size_val.setStyleSheet("color: #4ade80;")
            snap_meta_row.addWidget(snap_size_val)

        snap_meta_row.addStretch()

        snap_text.addWidget(snap_title)
        snap_text.addLayout(snap_meta_row)

        if self.entry.synced_at:
            snap_sync_row = QHBoxLayout()
            snap_sync_row.setSpacing(6)
            snap_sync_row.setContentsMargins(0, 0, 0, 0)

            snap_sync_icon = QLabel()
            snap_sync_icon.setPixmap(qta.icon(SYNC_GLYPH, color="#23a6ff").pixmap(14, 14))

            snap_sync_lbl = QLabel(tr("snapshots.last_sync").format(date=self.entry.synced_at.replace('T', 'T ', 1)))
            snap_sync_lbl.setFont(QFont("DejaVu Sans Mono", 9))
            snap_sync_lbl.setStyleSheet("color: #23a6ff;")

            snap_sync_row.addWidget(snap_sync_icon)
            snap_sync_row.addWidget(snap_sync_lbl)
            snap_sync_row.addStretch()
            snap_text.addLayout(snap_sync_row)

        snap_row.addWidget(snap_icon)
        snap_row.addLayout(snap_text)
        snap_row.addStretch()
        lbl_choose = QLabel(tr("snapshots.choose_restore_type"))
        lbl_choose.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        lbl_choose.setStyleSheet("color: #c8d4e0; letter-spacing: 1px;")
        btn1 = _RestoreOptionButton(
            glyph="mdi6.harddisk",
            title=tr("snapshots.restore_full_title"),
            desc=tr("snapshots.restore_full_desc"),
            color="#ff9966",
            parent=self,
            badge=tr("snapshots.restore_full_badge"),
        )
        btn1.clicked.connect(self._on_full_restore)

        btn2 = _RestoreOptionButton(
            glyph="mdi6.folder-search",
            title=tr("snapshots.restore_browser_title"),
            desc=tr("snapshots.restore_browser_desc"),
            color="#4ade80",
            parent=self,
        )
        btn2.clicked.connect(self._on_file_browser)

        btn3 = _RestoreOptionButton(
            glyph="mdi6.content-copy",
            title=tr("snapshots.restore_alt_title"),
            desc=tr("snapshots.restore_alt_desc"),
            color="#23a6ff",
            parent=self,
        )
        btn3.clicked.connect(self._on_alt_restore)

        is_home = self.entry.path.parent.name.upper() == "HOME"
        btn4 = None
        if is_home:
            btn4 = _RestoreOptionButton(
                glyph="mdi6.home-import-outline",
                title=tr("snapshots.restore_home_live_title"),
                desc=tr("snapshots.restore_home_live_desc"),
                color="#4ade80",
                parent=self,
            )
            btn4.clicked.connect(self._on_home_live_restore)

        b_layout.addLayout(snap_row)
        b_layout.addSpacing(24)
        b_layout.addWidget(lbl_choose)
        b_layout.addSpacing(10)
        b_layout.addWidget(btn1)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,10);")
        sep1.setFixedHeight(1)
        b_layout.addWidget(sep1)

        b_layout.addWidget(btn2)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,10);")
        sep2.setFixedHeight(1)
        b_layout.addWidget(sep2)

        b_layout.addWidget(btn3)

        if btn4 is not None:
            sep3 = QFrame()
            sep3.setFrameShape(QFrame.HLine)
            sep3.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,10);")
            sep3.setFixedHeight(1)
            b_layout.addWidget(sep3)
            b_layout.addWidget(btn4)

        b_layout.addStretch()

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #0d0f14;
                border-radius: 16px;
            }
            QFrame#RstHeader {
                background: rgba(35, 166, 255, 35);
                border-bottom: 1px solid rgba(35, 166, 255, 25);
                border-top-left-radius: 15px;
                border-top-right-radius: 15px;
            }
            QFrame#RstBody {
                background: #0d0f14;
                border-bottom-left-radius: 15px;
                border-bottom-right-radius: 15px;
            }
            QPushButton#RstClose {
                background: transparent; border: none;
                color: #6b7a8d; font-size: 13px; border-radius: 6px;
            }
            QPushButton#RstClose:hover {
                background: rgba(200,60,60,60); color: #ff8888;
            }
        """)

    def _on_full_restore(self) -> None:
        self.hide()
        try:
            _do_full_restore(self.entry, parent=self.parent())
        finally:
            self.show()

    def _on_file_browser(self) -> None:
        self.hide()
        dlg = _FileBrowserDialog(self.entry, parent=self.parent())
        dlg.exec()
        self.show()

    def _on_alt_restore(self) -> None:
        self.hide()
        dlg = _AltRestoreDialog(self.entry, parent=self.parent())
        dlg.exec()
        self.show()

    def _on_home_live_restore(self) -> None:
        self.hide()
        dlg = _HomeLiveRestoreDialog(self.entry, parent=self.parent())
        dlg.exec()
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen, QColor, QBrush
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(255, 255, 255, 22))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 16, 16)


class _RestoreOptionButton(QFrame):
    clicked = Signal()

    def __init__(self, glyph: str, title: str, desc: str, color: str, parent=None, badge: str = ""):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("RstOptionBtn")
        self.setFixedHeight(72)
        self._color = color
        self.setStyleSheet(f"""
            QFrame#RstOptionBtn {{
                background: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 10);
                border-radius: 12px;
            }}
            QFrame#RstOptionBtn:hover {{
                background: rgba(255, 255, 255, 9);
                border: 1px solid {color};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignVCenter)

        # Badge colorido via icon_badge
        ico_lbl = QLabel()
        ico_lbl.setFixedSize(42, 42)
        ico_lbl.setAlignment(Qt.AlignCenter)
        ico_lbl.setPixmap(qta.icon(glyph, color=color).pixmap(22, 22))
        h = color.lstrip("#")
        r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        ico_lbl.setStyleSheet(
            f"QLabel {{ background: rgba({r},{g},{b},40); "
            f"border-radius: 8px; border: 1px solid rgba({r},{g},{b},90); }}"
        )

        text = QVBoxLayout()
        text.setSpacing(1)
        text.setContentsMargins(0, 0, 0, 0)
        text.setAlignment(Qt.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.setContentsMargins(0, 0, 0, 0)

        t = QLabel(title)
        t.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        t.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        title_row.addWidget(t)

        if badge:
            badge_lbl = QLabel(badge.upper())
            badge_lbl.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
            badge_lbl.setStyleSheet(
                "color: #ff9966; background: rgba(255,153,102,22); "
                "border: 1px solid rgba(255,153,102,70); border-radius: 4px; "
                "padding: 1px 6px;"
            )
            title_row.addWidget(badge_lbl)

        title_row.addStretch()

        d = QLabel(desc)
        d.setFont(QFont("DejaVu Sans Mono", 9))
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


def _do_full_restore(entry: SnapshotEntry, parent=None) -> None:
    try:
        meta_file = entry.path / "snapshot.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        destination_mountpoint = meta.get("destination_mountpoint", "")
        backup_root = Path(meta.get("backup_root", ""))

        root_path = str(entry.path) if entry.kind == "ROOT" else None
        home_candidate = backup_root / "HOME" / entry.path.name
        home_path = str(home_candidate) if home_candidate.exists() else None

        if entry.kind == "HOME":
            root_candidate = backup_root / "ROOT" / entry.path.name
            root_path = str(root_candidate) if root_candidate.exists() else None
            home_path = str(entry.path)

        output = Path(destination_mountpoint) / "carbonara-restore.sh"
        output_instr = Path(destination_mountpoint) / "carbonara-restore-INSTRUCOES.txt"

        # Detecta ISO sugerida para incluir nas instruções
        ventoy = Path("/mnt/VENTOY")
        suggested_iso = "sua-iso-arch.iso"
        try:
            isos = sorted(
                [p for p in ventoy.iterdir() if p.suffix.lower() == ".iso"],
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            arch_isos = [p.name for p in isos if "arch" in p.name.lower()]
            suggested_iso = arch_isos[0] if arch_isos else (isos[0].name if isos else suggested_iso)
        except Exception:
            pass

        args_json = json.dumps({
            "root_path": root_path,
            "home_path": home_path,
            "output": str(output),
            "output_instr": str(output_instr),
            "suggested_iso": suggested_iso,
        })

        result = subprocess.run(
            [
                "pkexec",
                "/usr/local/bin/carbonara-helper",
                os.environ.get("DISPLAY", ""),
                os.environ.get("XAUTHORITY", ""),
                "restore.generate_script",
                args_json,
            ],
            capture_output=True, text=True,
        )

        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            if result.returncode == 126 or "dismissed" in err.lower():
                _show_error("Restore", tr("snapshots.delete_cancelled"), parent=parent)
            else:
                _show_error("Restore", f"Erro ao gerar script:\n\n{err}", parent=parent)
            return

        dlg = _RestoreInstructionsDialog(str(output), str(output_instr), parent=parent)
        dlg.exec()

    except Exception as e:
        _show_error("Restore", f"Erro ao gerar script:\n\n{e}", parent=parent)


class _RestoreInstructionsDialog(QDialog):
    def __init__(self, script_path: str, instructions_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("snapshots.instructions_dialog_title"))
        self.setModal(True)
        self.setFixedSize(820, 520)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._instructions_path = instructions_path
        self._build_ui(script_path)
        self._apply_styles()

    def _generate_instructions(self, script_path: str) -> str:
        """Gera arquivo de instruções legível salvo junto ao script."""
        import re
        script_dir = Path(script_path).parent
        out = script_dir / "carbonara-restore-INSTRUCOES.txt"
        iso_names = [p.name for p in self._find_ventoy_isos()]
        arch_isos = [n for n in iso_names if "arch" in n.lower()]
        suggested_iso = arch_isos[0] if arch_isos else (iso_names[0] if iso_names else "sua-iso-arch.iso")

        content = f"""
================================================================================
  CARBONARA — INSTRUÇÕES DE RESTORE COMPLETO DO SISTEMA
  Gerado em: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
================================================================================

PASSO 1 — Boot pelo Ventoy
  Reinicie o computador e selecione pelo Ventoy:
  → {suggested_iso}

PASSO 2 — Execute no shell do live ISO
  Cole o comando abaixo e pressione Enter:

  bash <(mount /dev/sdc3 /mnt/bk 2>/dev/null; cat /mnt/bk/carbonara-restore.sh)

  O script irá:
  ✓ Montar o disco de backup automaticamente
  ✓ Montar o array RAID0 (/dev/md127)
  ✓ Restaurar ROOT e HOME via rsync
  ✓ Reinstalar o GRUB (legacy BIOS)
  ✓ Desmontar tudo ao finalizar

PASSO 3 — Confirmação
  Quando solicitado, digite exatamente:  RESTAURAR
  (qualquer outra entrada cancela a operação)

================================================================================
  ARQUIVOS GERADOS
  Script:      {script_path}
  Instruções:  {str(out)}
================================================================================
""".strip()

        try:
            out.write_text(content, encoding="utf-8")
        except Exception:
            pass
        return str(out)

    def _build_ui(self, script_path: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("RIHeader")
        header.setFixedHeight(58)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 16, 0)

        icon = QLabel()
        icon.setFixedSize(38, 38)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.check-circle", color="#4ade80").pixmap(24, 24))
        icon.setStyleSheet("QLabel { background: rgba(74,222,128,30); border-radius: 10px; }")

        lbl = QLabel(tr("snapshots.instructions_dialog_title"))
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #4ade80;")

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()

        body = QFrame()
        body.setObjectName("RIBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 24, 28, 22)
        b_layout.setSpacing(8)

        # ── Passo 1: ISO disponível no Ventoy ────────────────────────────────
        lbl1 = QLabel(tr("snapshots.instructions_step1"))
        lbl1.setFont(QFont("DejaVu Sans Mono", 10))
        lbl1.setStyleSheet("color: #c8d4e0;")
        b_layout.addWidget(lbl1)

        isos = self._find_ventoy_isos()
        if isos:
            self.cmb_iso = QComboBox()
            self.cmb_iso.setFont(QFont("DejaVu Sans Mono", 10))
            for iso in isos:
                self.cmb_iso.addItem(iso.name)
            for i, iso in enumerate(isos):
                if "arch" in iso.name.lower():
                    self.cmb_iso.setCurrentIndex(i)
                    break
            self.cmb_iso.setStyleSheet("""
                QComboBox {
                    background: rgba(255,255,255,6);
                    border: 1px solid rgba(255,255,255,14);
                    border-radius: 10px; color: #ecf4ff;
                    font-family: "DejaVu Sans Mono"; font-size: 10px;
                    padding: 8px 12px;
                }
                QComboBox::drop-down { border: none; width: 20px; }
                QComboBox QAbstractItemView {
                    background: #0a0f19; color: #ecf4ff;
                    border: 1px solid rgba(255,255,255,14);
                }
            """)
            b_layout.addWidget(self.cmb_iso)
        else:
            lbl_no_iso = QLabel(tr("snapshots.instructions_no_iso"))
            lbl_no_iso.setFont(QFont("DejaVu Sans Mono", 10))
            lbl_no_iso.setStyleSheet("color: #ff9966;")
            b_layout.addWidget(lbl_no_iso)

        b_layout.addSpacing(20)

        # ── Passo 2: Executar script ──────────────────────────────────────────
        lbl2 = QLabel(tr("snapshots.instructions_step2"))
        lbl2.setFont(QFont("DejaVu Sans Mono", 10))
        lbl2.setStyleSheet("color: #c8d4e0;")
        b_layout.addWidget(lbl2)

        cmd_lbl = QLabel("bash <(mount /dev/sdc3 /mnt/bk 2>/dev/null; cat /mnt/bk/carbonara-restore.sh)")
        cmd_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        cmd_lbl.setWordWrap(True)
        cmd_lbl.setStyleSheet(
            "color: #8fd4ff; background: rgba(255,255,255,6); "
            "border: 1px solid rgba(255,255,255,14); border-radius: 10px; padding: 10px 14px;"
        )
        cmd_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_layout.addWidget(cmd_lbl)

        b_layout.addSpacing(4)

        lbl3 = QLabel(tr("snapshots.instructions_script_desc"))
        lbl3.setFont(QFont("DejaVu Sans Mono", 9))
        lbl3.setStyleSheet("color: #6b7a8d;")
        lbl3.setWordWrap(True)
        b_layout.addWidget(lbl3)

        warn_row = QHBoxLayout()
        warn_row.setSpacing(8)
        warn_row.setContentsMargins(0, 4, 0, 0)

        warn_icon = QLabel()
        warn_icon.setFixedSize(20, 20)
        warn_icon.setAlignment(Qt.AlignCenter)
        warn_icon.setPixmap(qta.icon("mdi6.alert", color="#ff9966").pixmap(18, 18))

        warn = QLabel(tr("snapshots.instructions_confirm_warning"))
        warn.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        warn.setStyleSheet("color: #ff9966;")

        warn_row.addWidget(warn_icon)
        warn_row.addWidget(warn)
        warn_row.addStretch()
        b_layout.addLayout(warn_row)

        b_layout.addSpacing(14)

        # ── Arquivos gerados ──────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,12);")
        b_layout.addWidget(sep)

        b_layout.addSpacing(6)

        lbl_files = QLabel(tr("snapshots.instructions_files_generated"))
        lbl_files.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        lbl_files.setStyleSheet("color: #c8d4e0;")
        b_layout.addWidget(lbl_files)

        lbl_script = QLabel(tr("snapshots.instructions_script_label").format(path=script_path))
        lbl_script.setFont(QFont("DejaVu Sans Mono", 9))
        lbl_script.setStyleSheet("color: #9aa6b2;")
        lbl_script.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_layout.addWidget(lbl_script)

        lbl_instr = QLabel(tr("snapshots.instructions_notes_label").format(path=self._instructions_path))
        lbl_instr.setFont(QFont("DejaVu Sans Mono", 9))
        lbl_instr.setStyleSheet("color: #9aa6b2;")
        lbl_instr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_layout.addWidget(lbl_instr)

        b_layout.addStretch()

        btn_ok = QPushButton("Entendido")
        btn_ok.setObjectName("RIBtnOk")
        btn_ok.setFixedWidth(120)
        btn_ok.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _find_ventoy_isos(self) -> list:
        """Lista ISOs em /mnt/VENTOY ordenadas por data (mais recente primeiro)."""
        ventoy = Path("/mnt/VENTOY")
        if not ventoy.exists():
            return []
        try:
            return sorted(
                [p for p in ventoy.iterdir() if p.suffix.lower() == ".iso"],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            return []

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#RIHeader {
                background: rgba(8, 20, 14, 255);
                border-bottom: 1px solid rgba(74, 222, 128, 35);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#RIBody {
                background: #131417;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#RIBtnOk {
                background: rgba(74, 222, 128, 180);
                border: 1px solid rgba(74, 222, 128, 220);
                border-radius: 8px; color: #08111d;
                font-family: "DejaVu Sans Mono";
                font-size: 11px; font-weight: 700; padding: 6px 0;
            }
            QPushButton#RIBtnOk:hover { background: rgba(94, 234, 149, 220); }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)




class _FileBrowserDialog(QDialog):
    """File browser para restaurar arquivos/pastas individuais do snapshot."""

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.snapshot_root = entry.path
        self.setWindowTitle(tr("snapshots.filebrowser_title"))
        self.setModal(True)
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowMaximizeButtonHint)
        self._current_path = self.snapshot_root
        self._selected_items = []
        self._conflict_mode = "overwrite"
        self._build_ui()
        self._apply_styles()
        self._populate_tree(self.snapshot_root)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("FBHeader")
        header.setFixedHeight(48)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 14, 0)
        hl.setSpacing(10)

        ico = QLabel()
        ico.setFixedSize(32, 32)
        ico.setAlignment(Qt.AlignCenter)
        ico.setPixmap(qta.icon("mdi6.folder-search", color="#4ade80").pixmap(22, 22))
        ico.setStyleSheet("QLabel { background: rgba(74,222,128,30); border-radius: 8px; }")

        lbl = QLabel(tr("snapshots.filebrowser_title"))
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        snap_lbl = QLabel(self.entry.path.name)
        snap_lbl.setFont(QFont("DejaVu Sans Mono", 8))
        snap_lbl.setStyleSheet("color: #6b7a8d;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()

        btn_max = _MaxLabel(self)

        hl.addWidget(ico)
        hl.addWidget(lbl)
        hl.addWidget(snap_lbl)
        hl.addStretch()
        hl.addWidget(btn_max)
        hl.addSpacing(4)
        hl.addWidget(btn_x)

        # Breadcrumb
        bc = QFrame()
        bc.setObjectName("FBBreadcrumb")
        bc.setFixedHeight(34)
        bcl = QHBoxLayout(bc)
        bcl.setContentsMargins(14, 0, 14, 0)
        bcl.setSpacing(6)

        self.btn_up = _NavLabel(self)
        self.btn_up.clicked.connect(self._go_up)
        self.btn_up.setEnabled(False)
        # Força reaplicação do estilo após o widget ser renderizado
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.btn_up.setEnabled(False))

        self.lbl_path = QLabel("/")
        self.lbl_path.setFont(QFont("DejaVu Sans Mono", 10))
        self.lbl_path.setStyleSheet("color: #9aa6b2;")

        bcl.addWidget(self.btn_up)
        bcl.addWidget(self.lbl_path, 1)

        # Corpo
        body = QFrame()
        body.setObjectName("FBBody")
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(12, 8, 12, 12)
        body_l.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background: rgba(255,255,255,18); }")

        # Árvore
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setObjectName("FBTree")
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setIconSize(QSize(24, 24))
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.setColumnCount(2)
        self.tree.header().hide()
        # Coluna 0 estica, coluna 1 (tamanho) largura fixa
        from PySide6.QtWidgets import QHeaderView
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.header().resizeSection(1, 80)

        # Painel direito
        right = QFrame()
        right.setObjectName("FBRight")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(8, 0, 0, 0)
        right_l.setSpacing(8)

        lbl_sel = QLabel(tr("snapshots.filebrowser_selected_label"))
        lbl_sel.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl_sel.setStyleSheet("color: #c8d4e0;")

        self.list_selected = QPlainTextEdit()
        self.list_selected.setReadOnly(True)
        self.list_selected.setObjectName("FBSelected")
        self.list_selected.setPlaceholderText(tr("snapshots.filebrowser_selected_placeholder"))

        # Conflito
        cf_frame = QFrame()
        cf_frame.setObjectName("FBConflict")
        cf_l = QVBoxLayout(cf_frame)
        cf_l.setContentsMargins(8, 8, 8, 8)
        cf_l.setSpacing(6)

        lbl_cf = QLabel(tr("snapshots.filebrowser_conflict_label"))
        lbl_cf.setFont(QFont("DejaVu Sans Mono", 9))
        lbl_cf.setStyleSheet("color: #9aa6b2;")

        self.btn_overwrite = QPushButton(tr("snapshots.filebrowser_overwrite"))
        self.btn_overwrite.setObjectName("FBConflictBtn")
        self.btn_overwrite.setCheckable(True)
        self.btn_overwrite.setChecked(True)
        self.btn_overwrite.clicked.connect(lambda: self._set_conflict("overwrite"))

        self.btn_skip = QPushButton(tr("snapshots.filebrowser_skip"))
        self.btn_skip.setObjectName("FBConflictBtn")
        self.btn_skip.setCheckable(True)
        self.btn_skip.clicked.connect(lambda: self._set_conflict("skip"))

        cf_l.addWidget(lbl_cf)
        cf_row = QHBoxLayout()
        cf_row.setSpacing(8)
        cf_row.addWidget(self.btn_overwrite)
        cf_row.addWidget(self.btn_skip)
        cf_l.addLayout(cf_row)

        self.btn_restore = QPushButton(tr("snapshots.filebrowser_btn_restore"))
        self.btn_restore.setIcon(qta.icon("mdi6.file-restore-outline", color="#08111d"))
        self.btn_restore.setIconSize(QSize(16, 16))
        self.btn_restore.setObjectName("FBBtnRestore")
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self._on_restore)

        right_l.addWidget(lbl_sel)
        right_l.addWidget(self.list_selected, 1)
        right_l.addWidget(cf_frame)
        right_l.addWidget(self.btn_restore)

        splitter.addWidget(self.tree)
        splitter.addWidget(right)
        splitter.setSizes([520, 350])

        body_l.addWidget(splitter, 1)

        # Log
        self.log_frame = QFrame()
        self.log_frame.setObjectName("FBLogFrame")
        self.log_frame.setVisible(False)
        log_l = QVBoxLayout(self.log_frame)
        log_l.setContentsMargins(0, 0, 0, 0)
        log_l.setSpacing(4)

        self.restore_progress = QProgressBar()
        self.restore_progress.setRange(0, 0)
        self.restore_progress.setFixedHeight(4)
        self.restore_progress.setTextVisible(False)
        self.restore_progress.setObjectName("FBProgressBar")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("FBLog")
        self.log_view.setFixedHeight(100)

        log_l.addWidget(self.restore_progress)
        log_l.addWidget(self.log_view)
        body_l.addWidget(self.log_frame)

        root.addWidget(header)
        root.addWidget(bc)
        root.addWidget(body, 1)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#FBHeader {
                background: rgba(8,20,14,255);
                border-bottom: 1px solid rgba(74,222,128,35);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QFrame#FBBreadcrumb {
                background: rgba(6,9,16,200);
                border-bottom: 1px solid rgba(255,255,255,16);
            }
            QFrame#FBBody {
                background: #131417;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QFrame#FBRight { background: transparent; }
            QFrame#FBConflict {
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px;
            }
            QFrame#FBLogFrame { background: transparent; }
            QPushButton#FBClose {
                background: transparent; border: none;
                color: #4a5a6a; font-size: 12px; border-radius: 6px;
            }
            QPushButton#FBClose:hover { background: rgba(200,60,60,60); color: #ff8888; }
            QPushButton#FBNavBtn {
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,18); border-radius: 8px;
            }
            QPushButton#FBNavBtn:hover {
                background: rgba(23,147,209,70);
                border-color: rgba(35,166,255,180);
            }
            QTreeWidget#FBTree {
                background: rgba(255,255,255,5);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px; color: #c8d4e0;
                font-family: "DejaVu Sans Mono"; font-size: 12px; outline: none;
            }
            QTreeWidget#FBTree::item { padding: 6px 8px; border-radius: 4px; }
            QTreeWidget#FBTree::item:hover { background: rgba(35,166,255,30); }
            QTreeWidget#FBTree::item:selected { background: rgba(35,166,255,80); color: #ecf4ff; }
            QPlainTextEdit#FBSelected {
                background: rgba(255,255,255,5);
                border: 1px solid rgba(255,255,255,18); border-radius: 10px;
                color: #9aa6b2; font-family: "DejaVu Sans Mono";
                font-size: 11px; padding: 6px;
            }
            QPlainTextEdit#FBLog {
                background: rgba(255,255,255,5);
                border: 1px solid rgba(255,255,255,16); border-radius: 8px;
                color: #6b7a8d; font-family: "DejaVu Sans Mono";
                font-size: 9px; padding: 4px;
            }
            QPushButton#FBConflictBtn {
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,18); border-radius: 10px;
                color: #9aa6b2; font-family: "DejaVu Sans Mono";
                font-size: 11px; padding: 8px 12px;
            }
            QPushButton#FBConflictBtn:checked {
                background: rgba(35,166,255,100);
                border-color: rgba(35,166,255,200); color: #ecf4ff;
            }
            QPushButton#FBBtnRestore {
                background: rgba(74,222,128,180);
                border: 1px solid rgba(74,222,128,220);
                border-radius: 10px; color: #08111d;
                font-family: "DejaVu Sans Mono"; font-size: 13px;
                font-weight: 700; padding: 11px 0;
            }
            QPushButton#FBBtnRestore:hover { background: rgba(94,234,149,220); }
            QPushButton#FBBtnRestore:disabled {
                background: rgba(30,40,30,180);
                border-color: rgba(74,222,128,40); color: #3a4a3a;
            }
            QProgressBar#FBProgressBar {
                background: rgba(255,255,255,10); border: none; border-radius: 2px;
            }
            QProgressBar#FBProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 rgba(74,222,128,200), stop:1 rgba(35,166,255,200));
                border-radius: 2px;
            }
        """)

    def _populate_tree(self, path):
        self.tree.clear()
        self._current_path = path
        try:
            rel = path.relative_to(self.snapshot_root)
            display = "/" + str(rel) if str(rel) != "." else "/"
        except ValueError:
            display = str(path)
        self.lbl_path.setText(display)
        self.btn_up.setEnabled(path != self.snapshot_root)

        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            if entry.name == "snapshot.json":
                continue
            item = self._make_item(entry)
            self.tree.addTopLevelItem(item)
            # Adiciona filho sentinel para pastas não vazias
            if entry.is_dir() and not entry.is_symlink():
                self._add_sentinel_if_needed(item, entry)

    def _make_item(self, entry: Path) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(0, entry.name)
        item.setData(0, Qt.UserRole, entry)
        item.setData(0, Qt.UserRole + 1, False)  # loaded = False
        if entry.is_symlink():
            item.setIcon(0, qta.icon("mdi6.link-variant", color="#9aa6b2"))
        elif entry.is_dir():
            item.setIcon(0, qta.icon("mdi6.folder", color="#23a6ff"))
        else:
            item.setIcon(0, self._file_icon(entry))
            try:
                item.setText(1, self._fmt_size(entry.stat().st_size))
            except OSError:
                pass
        return item

    def _add_sentinel_if_needed(self, item: QTreeWidgetItem, path: Path) -> None:
        """Adiciona filho placeholder se a pasta tiver conteúdo."""
        try:
            has_children = any(
                e for e in path.iterdir() if e.name != "snapshot.json"
            )
            if has_children:
                sentinel = QTreeWidgetItem()
                sentinel.setText(0, tr("snapshots.filebrowser_loading"))
                sentinel.setData(0, Qt.UserRole, None)  # marca sentinel
                sentinel.setDisabled(True)
                item.addChild(sentinel)
        except PermissionError:
            pass

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Popula filhos de uma pasta quando expandida (lazy loading)."""
        already_loaded = item.data(0, Qt.UserRole + 1)
        if already_loaded:
            return

        path: Path = item.data(0, Qt.UserRole)
        if not path or not path.is_dir():
            return

        # Remove sentinel
        item.takeChildren()

        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            if entry.name == "snapshot.json":
                continue
            child = self._make_item(entry)
            item.addChild(child)
            if entry.is_dir() and not entry.is_symlink():
                self._add_sentinel_if_needed(child, entry)

        item.setData(0, Qt.UserRole + 1, True)  # loaded = True

    def _file_icon(self, path):
        ext = path.suffix.lower()
        m = {
            ".py": ("mdi6.language-python", "#4ade80"),
            ".sh": ("mdi6.console", "#4ade80"),
            ".conf": ("mdi6.cog", "#9aa6b2"),
            ".json": ("mdi6.code-json", "#ff9966"),
            ".log": ("mdi6.text-box-outline", "#6b7a8d"),
            ".service": ("mdi6.cog-outline", "#9aa6b2"),
        }
        g, c = m.get(ext, ("mdi6.file-outline", "#6b7a8d"))
        return qta.icon(g, color=c)

    def _fmt_size(self, size):
        if size >= 1024**3: return f"{size/1024**3:.1f} GB"
        if size >= 1024**2: return f"{size/1024**2:.1f} MB"
        if size >= 1024: return f"{size/1024:.0f} KB"
        return f"{size} B"

    def _go_up(self):
        if self._current_path != self.snapshot_root:
            self._populate_tree(self._current_path.parent)

    def _on_double_click(self, item, col):
        path = item.data(0, Qt.UserRole)
        if path and path.is_dir() and not path.is_symlink():
            self._populate_tree(path)

    def _on_selection_changed(self):
        paths = [
            item.data(0, Qt.UserRole)
            for item in self.tree.selectedItems()
            if item.data(0, Qt.UserRole)
        ]
        self._selected_items = paths
        if paths:
            self.list_selected.setPlainText(
                "\n".join(str(p.relative_to(self.snapshot_root)) for p in paths)
            )
        else:
            self.list_selected.clear()
        self.btn_restore.setEnabled(bool(paths))

    def _set_conflict(self, mode):
        self._conflict_mode = mode
        self.btn_overwrite.setChecked(mode == "overwrite")
        self.btn_skip.setChecked(mode == "skip")

    def _on_restore(self):
        if not self._selected_items:
            return
        confirm = _ConfirmRestoreDialog(
            f"{len(self._selected_items)} item(ns)",
            self._conflict_mode, parent=self
        )
        if confirm.exec() != QDialog.Accepted:
            return

        args_json = json.dumps({
            "snapshot_root": str(self.snapshot_root),
            "items": [str(p) for p in self._selected_items],
            "conflict": self._conflict_mode,
            # Snapshot HOME armazena o conteúdo de /home/ sem o prefixo
            # "home/" — precisa recolocar esse prefixo no destino real.
            "dest_prefix": "home" if self.entry.kind.upper() == "HOME" else "",
        })

        self.log_frame.setVisible(True)
        self.log_view.clear()
        self.btn_restore.setEnabled(False)
        self.restore_progress.setRange(0, 0)

        worker = _FileBrowserRestoreWorker(
            args_json=args_json,
            parent=self,
        )
        worker.log_line.connect(self._on_log_line)
        worker.finished_ok.connect(self._on_restore_done)
        worker.failed.connect(self._on_restore_fail)
        self._restore_worker = worker
        worker.start()

    def _on_log_line(self, line):
        self.log_view.appendPlainText(line)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def _on_restore_done(self):
        self.restore_progress.setRange(0, 1)
        self.restore_progress.setValue(1)
        self.btn_restore.setEnabled(True)
        self._on_log_line(tr("snapshots.filebrowser_restore_done"))

    def _on_restore_fail(self, msg):
        self.restore_progress.setRange(0, 1)
        self.restore_progress.setValue(0)
        self.btn_restore.setEnabled(True)
        self._on_log_line(tr("snapshots.filebrowser_error").format(msg=msg))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(event.globalPosition().toPoint() - self._drag)


class _ConfirmRestoreDialog(QDialog):
    def __init__(self, label, conflict, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setFixedSize(440, 180)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("CRHeader")
        header.setFixedHeight(44)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 14, 0)
        ico = QLabel()
        ico.setFixedSize(24, 24)
        ico.setAlignment(Qt.AlignCenter)
        ico.setPixmap(qta.icon("mdi6.file-restore-outline", color="#4ade80").pixmap(16, 16))
        ico.setStyleSheet("QLabel { background: rgba(74,222,128,30); border-radius: 6px; }")
        lbl = QLabel(tr("snapshots.confirm_restore_title"))
        lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")
        hl.addWidget(ico)
        hl.addSpacing(8)
        hl.addWidget(lbl)
        hl.addStretch()

        body = QFrame()
        body.setObjectName("CRBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 14, 20, 16)
        bl.setSpacing(12)

        ct = (
            tr("snapshots.confirm_restore_overwriting") if conflict == "overwrite"
            else tr("snapshots.confirm_restore_skipping")
        )
        msg = QLabel(tr("snapshots.confirm_restore_message").format(label=label, ct=ct))
        msg.setFont(QFont("DejaVu Sans Mono", 9))
        msg.setStyleSheet("color: #c8d4e0;")

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton(tr("common.cancel"))
        btn_cancel.setObjectName("CRBtnCancel")
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(tr("common.restore"))
        btn_ok.setObjectName("CRBtnOk")
        btn_ok.setFixedWidth(100)
        btn_ok.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        bl.addWidget(msg)
        bl.addLayout(btn_row)
        root.addWidget(header)
        root.addWidget(body, 1)

        self.setStyleSheet("""
            QFrame#CRHeader {
                background: rgba(8,20,14,255);
                border-bottom: 1px solid rgba(74,222,128,80);
                border-top-left-radius: 10px; border-top-right-radius: 10px;
            }
            QFrame#CRBody {
                background: #080c14;
                border-bottom-left-radius: 10px; border-bottom-right-radius: 10px;
            }
            QPushButton#CRBtnCancel {
                background: rgba(10,15,25,230); border: 1px solid rgba(31,92,255,120);
                border-radius: 7px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono"; font-size: 10px; padding: 5px 0;
            }
            QPushButton#CRBtnCancel:hover { background: rgba(23,147,209,70); }
            QPushButton#CRBtnOk {
                background: rgba(74,222,128,180); border: 1px solid rgba(74,222,128,220);
                border-radius: 7px; color: #08111d;
                font-family: "DejaVu Sans Mono"; font-size: 10px;
                font-weight: 700; padding: 5px 0;
            }
            QPushButton#CRBtnOk:hover { background: rgba(94,234,149,220); }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(event.globalPosition().toPoint() - self._drag)


class _FileBrowserRestoreWorker(QThread):
    log_line = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, args_json: str, parent=None):
        super().__init__(parent)
        self._args_json = args_json

    def run(self):
        try:
            result = subprocess.run(
                [
                    "pkexec",
                    "/usr/local/bin/carbonara-helper",
                    os.environ.get("DISPLAY", ""),
                    os.environ.get("XAUTHORITY", ""),
                    "restore.copy_files",
                    self._args_json,
                ],
                capture_output=True, text=True,
            )
            for line in result.stdout.splitlines():
                if line.strip():
                    self.log_line.emit(line)
            if result.returncode != 0:
                err = result.stderr.strip() or f"exit code {result.returncode}"
                if result.returncode == 126 or "dismissed" in err.lower():
                    err = tr("snapshots.delete_cancelled")
                self.failed.emit(err)
            else:
                self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))



# ── Alt Restore helpers ───────────────────────────────────────────────────────

class _AltRestoreDialog(QDialog):
    """Dialog para restaurar snapshot para um disco alternativo."""

    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(tr("snapshots.altrestore_title"))
        self.setModal(True)
        self.setFixedSize(800, 480)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._destinations = []
        self._build_ui()
        self._apply_styles()
        self._load_destinations()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("ARHeader")
        header.setFixedHeight(60)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 18, 0)

        ico = QLabel()
        ico.setFixedSize(40, 40)
        ico.setAlignment(Qt.AlignCenter)
        ico.setPixmap(qta.icon("mdi6.content-copy", color="#23a6ff").pixmap(24, 24))
        ico.setStyleSheet("QLabel { background: rgba(35,166,255,40); border-radius: 10px; }")

        lbl = QLabel(tr("snapshots.altrestore_title"))
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()

        hl.addWidget(ico)
        hl.addSpacing(10)
        hl.addWidget(lbl)
        hl.addStretch()
        hl.addWidget(btn_x)

        # Body
        body = QFrame()
        body.setObjectName("ARBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(28, 24, 28, 24)
        bl.setSpacing(14)

        # Snapshot info
        snap_row = QHBoxLayout()
        snap_row.setSpacing(14)
        snap_row.setContentsMargins(0, 0, 0, 0)

        snap_icon = icon_badge(SNAPSHOT_GLYPH, 38)

        snap_text = QVBoxLayout()
        snap_text.setSpacing(4)
        snap_text.setContentsMargins(0, 0, 0, 0)

        snap_title = QLabel(self.entry.path.name)
        snap_title_font = QFont("DejaVu Sans Mono")
        snap_title_font.setPointSizeF(10.5)
        snap_title_font.setBold(True)
        snap_title.setFont(snap_title_font)
        snap_title.setStyleSheet("color: #ecf4ff;")

        snap_meta_row = QHBoxLayout()
        snap_meta_row.setSpacing(8)
        snap_meta_row.setContentsMargins(0, 0, 0, 0)

        snap_meta = QLabel(self.entry.meta_text)
        snap_meta.setFont(QFont("DejaVu Sans Mono", 10))
        snap_meta.setStyleSheet("color: #6b7a8d;")
        snap_meta_row.addWidget(snap_meta)

        if self.entry.size_str:
            snap_size_prefix = QLabel(tr("snapshots.size_label"))
            snap_size_prefix.setFont(QFont("DejaVu Sans Mono", 9))
            snap_size_prefix.setStyleSheet("color: #6b7a8d;")
            snap_meta_row.addWidget(snap_size_prefix)

            snap_size_val = QLabel(self.entry.size_str)
            snap_size_val.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
            snap_size_val.setStyleSheet("color: #4ade80;")
            snap_meta_row.addWidget(snap_size_val)

        snap_meta_row.addStretch()

        snap_text.addWidget(snap_title)
        snap_text.addLayout(snap_meta_row)

        if self.entry.synced_at:
            snap_sync_row = QHBoxLayout()
            snap_sync_row.setSpacing(6)
            snap_sync_row.setContentsMargins(0, 0, 0, 0)

            snap_sync_icon = QLabel()
            snap_sync_icon.setPixmap(qta.icon(SYNC_GLYPH, color="#23a6ff").pixmap(14, 14))

            snap_sync_lbl = QLabel(tr("snapshots.last_sync").format(date=self.entry.synced_at.replace('T', 'T ', 1)))
            snap_sync_lbl.setFont(QFont("DejaVu Sans Mono", 9))
            snap_sync_lbl.setStyleSheet("color: #23a6ff;")

            snap_sync_row.addWidget(snap_sync_icon)
            snap_sync_row.addWidget(snap_sync_lbl)
            snap_sync_row.addStretch()
            snap_text.addLayout(snap_sync_row)

        snap_row.addWidget(snap_icon)
        snap_row.addLayout(snap_text)
        snap_row.addStretch()

        # Destino
        lbl_dest = QLabel(tr("snapshots.altrestore_select_dest"))
        lbl_dest.setFont(QFont("DejaVu Sans Mono", 10))
        lbl_dest.setStyleSheet("color: #c8d4e0;")

        self.cmb_dest = QComboBox()
        self.cmb_dest.setFont(QFont("DejaVu Sans Mono", 10))
        self.cmb_dest.setMinimumHeight(40)
        style_combo_popup(self.cmb_dest)

        # Opções de cópia
        lbl_opts = QLabel(tr("snapshots.altrestore_options_label"))
        lbl_opts.setFont(QFont("DejaVu Sans Mono", 10))
        lbl_opts.setStyleSheet("color: #c8d4e0;")

        opts_row = QHBoxLayout()
        opts_row.setSpacing(10)

        self.chk_delete = QPushButton(tr("snapshots.altrestore_opt_delete"))
        self.chk_delete.setCheckable(True)
        self.chk_delete.setChecked(False)
        self.chk_delete.setObjectName("AROptBtn")
        self.chk_delete.setFixedHeight(38)
        self.chk_delete.setMinimumWidth(200)
        self.chk_delete.setCursor(Qt.PointingHandCursor)

        self.chk_hardlinks = QPushButton(tr("snapshots.altrestore_opt_hardlinks"))
        self.chk_hardlinks.setCheckable(True)
        self.chk_hardlinks.setChecked(True)
        self.chk_hardlinks.setObjectName("AROptBtn")
        self.chk_hardlinks.setFixedHeight(38)
        self.chk_hardlinks.setMinimumWidth(200)
        self.chk_hardlinks.setCursor(Qt.PointingHandCursor)

        opts_row.addWidget(self.chk_delete)
        opts_row.addWidget(self.chk_hardlinks)
        opts_row.addStretch()

        # Info destino
        self.lbl_dest_info = QLabel("—")
        self.lbl_dest_info.setFont(QFont("DejaVu Sans Mono", 9))
        self.lbl_dest_info.setStyleSheet("color: #6b7a8d;")
        self.lbl_dest_info.setWordWrap(True)
        self.cmb_dest.currentIndexChanged.connect(self._on_dest_changed)

        # Warn
        warn_row = QHBoxLayout()
        warn_row.setSpacing(8)
        warn_row.setContentsMargins(0, 0, 0, 0)

        warn_icon = QLabel()
        warn_icon.setFixedSize(20, 20)
        warn_icon.setAlignment(Qt.AlignCenter)
        warn_icon.setPixmap(qta.icon("mdi6.alert", color="#ff9966").pixmap(18, 18))

        warn = QLabel(tr("snapshots.altrestore_warning"))
        warn.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        warn.setStyleSheet("color: #ff9966;")

        warn_row.addWidget(warn_icon)
        warn_row.addWidget(warn)
        warn_row.addStretch()

        # Botões
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_cancel = QPushButton(tr("common.cancel"))
        btn_cancel.setObjectName("ARBtnCancel")
        btn_cancel.setFixedSize(120, 40)
        btn_cancel.clicked.connect(self.reject)

        self.btn_start = QPushButton(tr("snapshots.altrestore_btn_start"))
        self.btn_start.setObjectName("ARBtnStart")
        self.btn_start.setFixedSize(160, 40)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_start)

        bl.addLayout(snap_row)
        bl.addSpacing(6)
        bl.addWidget(lbl_dest)
        bl.addWidget(self.cmb_dest)
        bl.addWidget(self.lbl_dest_info)
        bl.addSpacing(4)
        bl.addWidget(lbl_opts)
        bl.addLayout(opts_row)
        bl.addSpacing(20)
        bl.addLayout(warn_row)
        bl.addStretch()
        bl.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#ARHeader {
                background: rgba(35, 166, 255, 35);
                border-bottom: 1px solid rgba(35, 166, 255, 25);
                border-top-left-radius: 13px;
                border-top-right-radius: 13px;
            }
            QFrame#ARBody {
                background: #131417;
                border-bottom-left-radius: 13px;
                border-bottom-right-radius: 13px;
            }
            QComboBox {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono"; padding: 8px 12px;
            }
            QComboBox:hover { border-color: rgba(35,166,255,200); }
            QComboBox::drop-down { border: none; width: 24px; }
            QPushButton#AROptBtn {
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px; color: #9aa6b2;
                font-family: "DejaVu Sans Mono"; font-size: 10px;
                padding: 0 14px;
            }
            QPushButton#AROptBtn:checked {
                background: rgba(74,222,128,100);
                border-color: rgba(74,222,128,200); color: #ffffff;
            }
            QPushButton#ARBtnCancel {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px; color: #ecf4ff;
                font-family: "DejaVu Sans Mono"; font-size: 11px;
            }
            QPushButton#ARBtnCancel:hover {
                background: rgba(23,147,209,70);
                border-color: rgba(35,166,255,180);
            }
            QPushButton#ARBtnStart {
                background: rgba(35,166,255,180);
                border: 1px solid rgba(35,166,255,220);
                border-radius: 10px; color: #08111d;
                font-family: "DejaVu Sans Mono"; font-size: 11px;
                font-weight: 700;
            }
            QPushButton#ARBtnStart:hover { background: rgba(70,188,255,220); }
            QPushButton#ARBtnStart:disabled {
                background: rgba(255,255,255,6);
                border-color: rgba(255,255,255,14); color: #3a4a5a;
            }
        """)

    def _load_destinations(self):
        """Lista discos montados excluindo o disco de origem do snapshot."""
        snap_mount = None
        try:
            meta = json.loads((self.entry.path / "snapshot.json").read_text())
            snap_mount = meta.get("destination_mountpoint", "")
        except Exception:
            pass

        self.cmb_dest.clear()
        self._destinations = []

        for dest in list_backup_destinations():
            if dest.mountpoint == snap_mount:
                continue  # exclui o disco onde o snapshot está
            self._destinations.append(dest)
            label = tr("snapshots.altrestore_combo_item").format(
                label=dest.label, free=format_gb(dest.free_gb), mountpoint=dest.mountpoint,
            )
            self.cmb_dest.addItem(label, dest)

        self.btn_start.setEnabled(bool(self._destinations))
        if not self._destinations:
            self.lbl_dest_info.setText(tr("snapshots.altrestore_no_disks"))
        else:
            self._on_dest_changed(0)

    def _on_dest_changed(self, index: int):
        if index < 0 or index >= len(self._destinations):
            return
        dest = self._destinations[index]
        base_info = tr("snapshots.altrestore_dest_info").format(
            free=format_gb(dest.free_gb), total=format_gb(dest.total_gb), fs_type=dest.fs_type,
        )

        if self.entry.size_gb > 0 and dest.free_gb < self.entry.size_gb:
            self.lbl_dest_info.setText(
                tr("snapshots.altrestore_insufficient_space").format(
                    base_info=base_info, size=self.entry.size_str,
                    missing=format_gb(self.entry.size_gb - dest.free_gb),
                )
            )
            self.lbl_dest_info.setStyleSheet("color: #ff8888; font-weight: bold;")
            self.btn_start.setEnabled(False)
        else:
            self.lbl_dest_info.setText(base_info)
            self.lbl_dest_info.setStyleSheet("color: #6b7a8d;")
            self.btn_start.setEnabled(True)

    def _on_start(self):
        idx = self.cmb_dest.currentIndex()
        if idx < 0 or idx >= len(self._destinations):
            return
        dest = self._destinations[idx]

        use_delete = self.chk_delete.isChecked()
        use_hardlinks = self.chk_hardlinks.isChecked()

        self.accept()

        args_json = json.dumps({
            "snap_path": str(self.entry.path),
            "dest_path": dest.mountpoint,
            "dest_label": dest.label,
            "use_delete": use_delete,
            "use_hardlinks": use_hardlinks,
        })

        cmd_pkexec = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "restore.copy_to_alt_disk",
            args_json,
        ]

        try:
            subprocess.Popen(cmd_pkexec)
        except Exception as e:
            _show_error("Restore Alternativo", str(e), parent=self.parent())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(event.globalPosition().toPoint() - self._drag)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen, QColor
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(31, 141, 218, 120))
        pen.setWidth(1)
        painter.setPen(pen)
        from PySide6.QtCore import Qt as _Qt
        painter.setBrush(_Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 14, 14)

# ── Sync helpers ─────────────────────────────────────────────────────────────

class _HomeLiveRestoreDialog(QDialog):
    """Confirmação pro restore de HOME sem reboot — checkbox obrigatório
    (o Confirmar só habilita depois de marcado), dispara e esquece igual
    ao _AltRestoreDialog (o próprio processo pkexec abre o
    BackupProgressDialog como root na tela do usuário)."""

    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(tr("snapshots.home_live_title"))
        self.setModal(True)
        self.setFixedSize(560, 300)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(entry)
        self._apply_styles()

    def _build_ui(self, entry: SnapshotEntry) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("HomeRestoreHeader")
        header.setFixedHeight(56)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 18, 0)

        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.home-import-outline", color="#ffcf8f").pixmap(22, 22))
        icon.setStyleSheet("QLabel { background: rgba(224,168,64,40); border-radius: 9px; }")

        lbl = QLabel(tr("snapshots.home_live_title"))
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
        body.setObjectName("HomeRestoreBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 22, 28, 22)
        b_layout.setSpacing(12)

        warn = QLabel(tr("snapshots.home_live_warning"))
        warn.setWordWrap(True)
        warn.setFont(QFont("DejaVu Sans Mono", 9))
        warn.setStyleSheet("color: #c8d4e0;")

        snap_label = QLabel(entry.path.name)
        snap_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        snap_label.setStyleSheet(
            "color: #ffcf8f; background: #101115; "
            "border-radius: 6px; padding: 10px 12px;"
        )

        self.chk_confirm = QCheckBox(tr("snapshots.home_live_checkbox"))
        self.chk_confirm.setObjectName("HomeRestoreCheck")
        self.chk_confirm.setFont(QFont("DejaVu Sans Mono", 9))
        self.chk_confirm.toggled.connect(self._on_checkbox_toggled)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton(tr("common.cancel"))
        btn_cancel.setObjectName("HomeRestoreBtnCancel")
        btn_cancel.setFixedSize(110, 40)
        btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton(tr("snapshots.home_live_confirm"))
        self.btn_confirm.setObjectName("HomeRestoreBtnConfirm")
        self.btn_confirm.setFixedSize(130, 40)
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self._on_confirm)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_confirm)

        b_layout.addWidget(warn)
        b_layout.addSpacing(6)
        b_layout.addWidget(snap_label)
        b_layout.addSpacing(6)
        b_layout.addWidget(self.chk_confirm)
        b_layout.addStretch()
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _on_checkbox_toggled(self, checked: bool) -> None:
        self.btn_confirm.setEnabled(checked)

    def _on_confirm(self) -> None:
        if not self.chk_confirm.isChecked():
            return
        self.accept()

        args_json = json.dumps({"home_snapshot_path": str(self.entry.path)})
        cmd_pkexec = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "restore.home_live",
            args_json,
        ]

        try:
            subprocess.Popen(cmd_pkexec)
        except Exception as e:
            _show_error("Restaurar HOME", str(e), parent=self.parent())

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#HomeRestoreHeader {
                background: rgba(224, 168, 64, 35);
                border-bottom: 1px solid rgba(224, 168, 64, 25);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QFrame#HomeRestoreBody {
                background: #131417;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QCheckBox#HomeRestoreCheck {
                color: #c8d4e0;
                spacing: 8px;
            }
            QCheckBox#HomeRestoreCheck::indicator {
                width: 16px; height: 16px;
                border: 1px solid rgba(224,168,64,120);
                border-radius: 4px;
                background: rgba(255,255,255,6);
            }
            QCheckBox#HomeRestoreCheck::indicator:checked {
                background: rgba(224,168,64,200);
                border: 1px solid rgba(224,168,64,220);
            }
            QPushButton#HomeRestoreBtnCancel {
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,20);
                border-radius: 10px;
                color: #c8d4e0;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
            }
            QPushButton#HomeRestoreBtnCancel:hover {
                background: rgba(255,255,255,14);
            }
            QPushButton#HomeRestoreBtnConfirm {
                background: rgba(224, 168, 64, 180);
                border: 1px solid rgba(224, 168, 64, 220);
                border-radius: 10px;
                color: #1a1200;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#HomeRestoreBtnConfirm:hover {
                background: rgba(240, 190, 90, 220);
            }
            QPushButton#HomeRestoreBtnConfirm:disabled {
                background: rgba(224, 168, 64, 40);
                color: rgba(26, 18, 0, 140);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(event.globalPosition().toPoint() - self._drag)


class _SyncConfirmDialog(QDialog):
    """Dialog de confirmação estilizado para sync de snapshot."""

    def __init__(self, entry: SnapshotEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("snapshots.sync_confirm_title"))
        self.setModal(True)
        self.setFixedSize(540, 240)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(entry)
        self._apply_styles()

    def _build_ui(self, entry: SnapshotEntry) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("SyncHeader")
        header.setFixedHeight(56)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 18, 0)

        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.sync", color="#9bf0bd").pixmap(22, 22))
        icon.setStyleSheet("QLabel { background: rgba(74,222,128,40); border-radius: 9px; }")

        lbl = QLabel(tr("snapshots.sync_confirm_header"))
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
        body.setObjectName("SyncBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 22, 28, 22)
        b_layout.setSpacing(12)

        warn = QLabel(tr("snapshots.sync_confirm_warning"))
        warn.setWordWrap(True)
        warn.setFont(QFont("DejaVu Sans Mono", 9))
        warn.setStyleSheet("color: #c8d4e0;")

        snap_label = QLabel(entry.path.name)
        snap_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        snap_label.setStyleSheet(
            "color: #23a6ff; background: #101115; "
            "border-radius: 6px; padding: 10px 12px;"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton(tr("common.cancel"))
        btn_cancel.setObjectName("SyncBtnCancel")
        btn_cancel.setFixedSize(110, 40)
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton(tr("snapshots.sync_confirm_button"))
        btn_confirm.setObjectName("SyncBtnConfirm")
        btn_confirm.setFixedSize(130, 40)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)

        b_layout.addWidget(warn)
        b_layout.addSpacing(6)
        b_layout.addWidget(snap_label)
        b_layout.addStretch()
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#SyncHeader {
                background: rgba(74, 222, 128, 35);
                border-bottom: 1px solid rgba(74, 222, 128, 25);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QFrame#SyncBody {
                background: #131417;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QPushButton#SyncClose {
                background: transparent;
                border: none;
                color: #4a5a6a;
                font-size: 12px;
                border-radius: 6px;
            }
            QPushButton#SyncClose:hover {
                background: rgba(200, 60, 60, 60);
                color: #ff8888;
            }
            QPushButton#SyncBtnCancel {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
            }
            QPushButton#SyncBtnCancel:hover {
                background: rgba(23, 147, 209, 70);
                border-color: rgba(35, 166, 255, 180);
            }
            QPushButton#SyncBtnConfirm {
                background: rgba(74, 222, 128, 180);
                border: 1px solid rgba(74, 222, 128, 220);
                border-radius: 10px;
                color: #08111d;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#SyncBtnConfirm:hover {
                background: rgba(94, 234, 149, 220);
                border-color: rgba(94, 234, 149, 255);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


class _OfferPairSyncDialog(QDialog):
    """Exibido após um SYNC bem-sucedido, perguntando se o usuário quer
    sincronizar também o snapshot irmão (ROOT ↔ HOME) de mesmo stamp."""

    def __init__(
        self,
        sibling_kind: str,
        sibling_name: str,
        parent=None,
        title: str | None = None,
        message: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title or tr("snapshots.pair_sync_title"))
        self.setModal(True)
        self.setFixedSize(540, 240)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(sibling_kind, sibling_name, title, message)
        self._apply_styles()

    def _build_ui(
        self,
        sibling_kind: str,
        sibling_name: str,
        title: str | None = None,
        message: str | None = None,
    ) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("SyncHeader")
        header.setFixedHeight(56)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 18, 0)

        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.sync", color="#9bf0bd").pixmap(22, 22))
        icon.setStyleSheet("QLabel { background: rgba(74,222,128,40); border-radius: 9px; }")

        lbl = QLabel(title or tr("snapshots.pair_sync_title"))
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
        body.setObjectName("SyncBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 22, 28, 22)
        b_layout.setSpacing(12)

        msg = QLabel(
            message or tr("snapshots.pair_sync_message").format(kind=sibling_kind)
        )
        msg.setWordWrap(True)
        msg.setFont(QFont("DejaVu Sans Mono", 9))
        msg.setStyleSheet("color: #c8d4e0;")

        snap_label = QLabel(f"{sibling_kind} • {sibling_name}")
        snap_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        snap_label.setStyleSheet(
            "color: #23a6ff; background: #101115; "
            "border-radius: 6px; padding: 10px 12px;"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton(tr("snapshots.pair_sync_cancel"))
        btn_cancel.setObjectName("SyncBtnCancel")
        btn_cancel.setFixedSize(130, 40)
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton(tr("snapshots.pair_sync_confirm").format(kind=sibling_kind))
        btn_confirm.setObjectName("SyncBtnConfirm")
        btn_confirm.setFixedSize(170, 40)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)

        b_layout.addWidget(msg)
        b_layout.addSpacing(6)
        b_layout.addWidget(snap_label)
        b_layout.addStretch()
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#SyncHeader {
                background: rgba(74, 222, 128, 35);
                border-bottom: 1px solid rgba(74, 222, 128, 25);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QFrame#SyncBody {
                background: #131417;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QPushButton#SyncBtnCancel {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
            }
            QPushButton#SyncBtnCancel:hover {
                background: rgba(23, 147, 209, 70);
                border-color: rgba(35, 166, 255, 180);
            }
            QPushButton#SyncBtnConfirm {
                background: rgba(74, 222, 128, 180);
                border: 1px solid rgba(74, 222, 128, 220);
                border-radius: 10px;
                color: #08111d;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#SyncBtnConfirm:hover {
                background: rgba(94, 234, 149, 220);
                border-color: rgba(94, 234, 149, 255);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


class _VerifySelectDialog(QDialog):
    """Mostrado ao clicar em VERIFICAR — lista todos os snapshots ROOT/HOME
    disponíveis com checkboxes, permitindo escolher exatamente quais serão
    checados de verdade (rsync --dry-run). Por padrão só o mais recente de
    cada tipo vem pré-marcado, mas o usuário pode marcar snapshots antigos
    também."""

    @staticmethod
    def make_id(entry: SnapshotEntry) -> str:
        return f"{entry.kind.upper()}::{entry.path.name}"

    def __init__(self, entries: list[SnapshotEntry], default_checked: set[str], parent=None):
        super().__init__(parent)
        self.entries = entries
        self.checkboxes: dict[str, QCheckBox] = {}
        self.setWindowTitle(tr("snapshots.verify_select_title"))
        self.setModal(True)
        row_h = 30
        self.setFixedSize(560, 240 + row_h * max(0, len(entries) - 1))
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(default_checked)
        self._apply_styles()

    def selected_entries(self) -> list[SnapshotEntry]:
        return [e for e in self.entries if self.checkboxes[self.make_id(e)].isChecked()]

    def _build_ui(self, default_checked: set[str]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("SelHeader")
        header.setFixedHeight(56)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 18, 0)

        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon(VERIFY_GLYPH, color="#9bf0bd").pixmap(22, 22))
        icon.setStyleSheet("QLabel { background: rgba(155,240,189,40); border-radius: 9px; }")

        lbl = QLabel(tr("snapshots.verify_select_title"))
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
        body.setObjectName("SelBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 20, 28, 20)
        b_layout.setSpacing(10)

        msg_text = tr("snapshots.verify_select_msg")
        msg = QLabel(msg_text)
        msg.setWordWrap(True)
        msg_font = QFont("DejaVu Sans Mono", 9)
        msg.setFont(msg_font)
        msg.setStyleSheet("color: #c8d4e0; line-height: 150%;")
        msg_rect = QFontMetrics(msg_font).boundingRect(QRect(0, 0, 560 - 28 - 28, 0), Qt.TextWordWrap, msg_text)
        msg.setFixedHeight(msg_rect.height() + 14)
        b_layout.addWidget(msg)
        b_layout.addSpacing(4)

        for e in sorted(self.entries, key=lambda x: (x.kind.upper(), x.path.name), reverse=True):
            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            id_ = self.make_id(e)
            cb = QCheckBox()
            cb.setChecked(id_ in default_checked)
            cb.setObjectName("SyncCheckbox")
            self.checkboxes[id_] = cb

            snap_label = QLabel(f"{e.kind.upper()} • {e.path.name}")
            snap_label.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
            snap_label.setStyleSheet(
                "color: #23a6ff; background: #101115; "
                "border-radius: 6px; padding: 7px 10px;"
            )

            row_layout.addWidget(cb)
            row_layout.addWidget(snap_label, 1)
            b_layout.addWidget(row)

        b_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton(tr("common.cancel"))
        btn_cancel.setObjectName("SyncBtnCancel")
        btn_cancel.setFixedSize(130, 40)
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton(tr("snapshots.verify_select_confirm"))
        btn_confirm.setObjectName("SyncBtnConfirm")
        btn_confirm.setFixedSize(200, 40)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#SelHeader {
                background: rgba(155, 240, 189, 35);
                border-bottom: 1px solid rgba(155, 240, 189, 25);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QFrame#SelBody {
                background: #131417;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QCheckBox#SyncCheckbox {
                spacing: 0px;
            }
            QCheckBox#SyncCheckbox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid rgba(255,255,255,40);
                background: rgba(255,255,255,6);
            }
            QCheckBox#SyncCheckbox::indicator:checked {
                background: rgba(180, 250, 210, 220);
                border: 1px solid rgba(180, 250, 210, 255);
                image: url(__CHECK_ICON__);
            }
            QPushButton#SyncBtnCancel {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
            }
            QPushButton#SyncBtnCancel:hover {
                background: rgba(23, 147, 209, 70);
                border-color: rgba(35, 166, 255, 180);
            }
            QPushButton#SyncBtnConfirm {
                background: rgba(155, 240, 189, 180);
                border: 1px solid rgba(155, 240, 189, 220);
                border-radius: 10px;
                color: #08111d;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#SyncBtnConfirm:hover {
                background: rgba(180, 250, 210, 220);
                border-color: rgba(180, 250, 210, 255);
            }
        """.replace("__CHECK_ICON__", _checkbox_check_icon_path()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


class _VerifyResultsDialog(QDialog):
    """Exibido após o botão VERIFICAR encontrar um ou mais snapshots
    desatualizados. Mostra todos de uma vez com checkboxes, em vez de
    perguntar um por um — evita o efeito "insistente" de vários dialogs
    em sequência."""

    def __init__(self, stale: list[tuple[str, str]], parent=None):
        # stale: lista de (kind, snapshot_name), ex: [("ROOT", "2026-..."), ("HOME", "2026-...")]
        super().__init__(parent)
        self.stale = stale
        self.checkboxes: dict[str, QCheckBox] = {}
        self.setWindowTitle(tr("snapshots.verify_results_title_single"))
        self.setModal(True)
        self.setFixedSize(540, 260 + 34 * max(0, len(stale) - 1))
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui()
        self._apply_styles()

    def selected_kinds(self) -> list[str]:
        return [key for key, cb in self.checkboxes.items() if cb.isChecked()]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("SyncHeader")
        header.setFixedHeight(56)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 18, 0)

        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.sync-alert", color="#e0a840").pixmap(22, 22))
        icon.setStyleSheet("QLabel { background: rgba(224,168,64,40); border-radius: 9px; }")

        kinds_involved = {kind for kind, _ in self.stale}
        if len(self.stale) > 1 and len(kinds_involved) > 1:
            title_text = tr("snapshots.verify_results_title_both")
        elif len(self.stale) > 1:
            title_text = tr("snapshots.verify_results_title_multi").format(
                count=len(self.stale), kind=next(iter(kinds_involved))
            )
        else:
            title_text = tr("snapshots.verify_results_title_single").format(kind=self.stale[0][0])
        lbl = QLabel(title_text)
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
        body.setObjectName("SyncBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(28, 22, 28, 22)
        b_layout.setSpacing(12)

        msg = QLabel(tr("snapshots.verify_results_msg"))
        msg.setWordWrap(True)
        msg.setFont(QFont("DejaVu Sans Mono", 9))
        msg.setStyleSheet("color: #c8d4e0;")
        b_layout.addWidget(msg)
        b_layout.addSpacing(4)

        for kind, name in self.stale:
            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            key = f"{kind}|{name}"
            cb = QCheckBox()
            cb.setChecked(True)
            cb.setObjectName("SyncCheckbox")
            cb.stateChanged.connect(self._update_confirm_label)
            self.checkboxes[key] = cb

            snap_label = QLabel(f"{kind} • {name}")
            snap_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
            snap_label.setStyleSheet(
                "color: #23a6ff; background: #101115; "
                "border-radius: 6px; padding: 10px 12px;"
            )

            row_layout.addWidget(cb)
            row_layout.addWidget(snap_label, 1)
            b_layout.addWidget(row)

        b_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton(tr("snapshots.verify_results_cancel"))
        btn_cancel.setObjectName("SyncBtnCancel")
        btn_cancel.setFixedSize(130, 40)
        btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton()
        self.btn_confirm.setObjectName("SyncBtnConfirm")
        self.btn_confirm.setFixedSize(190, 40)
        self.btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_confirm)

        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

        self._update_confirm_label()

    def _update_confirm_label(self) -> None:
        selected = self.selected_kinds()
        if len(selected) == 0:
            self.btn_confirm.setText(tr("snapshots.verify_results_sync"))
            self.btn_confirm.setEnabled(False)
        elif len(selected) == len(self.stale) and len(self.stale) > 1:
            self.btn_confirm.setText(tr("snapshots.verify_results_sync_all").format(count=len(selected)))
            self.btn_confirm.setEnabled(True)
        elif len(selected) == 1:
            kind = selected[0].split("|", 1)[0]
            self.btn_confirm.setText(tr("snapshots.verify_results_sync_one").format(kind=kind))
            self.btn_confirm.setEnabled(True)
        else:
            self.btn_confirm.setText(tr("snapshots.verify_results_sync_n").format(count=len(selected)))
            self.btn_confirm.setEnabled(True)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #131417;
                border-radius: 14px;
            }
            QFrame#SyncHeader {
                background: rgba(224, 168, 64, 35);
                border-bottom: 1px solid rgba(224, 168, 64, 25);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
            QFrame#SyncBody {
                background: #131417;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QCheckBox#SyncCheckbox {
                spacing: 0px;
            }
            QCheckBox#SyncCheckbox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid rgba(255,255,255,40);
                background: rgba(255,255,255,6);
            }
            QCheckBox#SyncCheckbox::indicator:checked {
                background: rgba(74, 222, 128, 200);
                border: 1px solid rgba(74, 222, 128, 220);
                image: url(__CHECK_ICON__);
            }
            QPushButton#SyncBtnCancel {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
            }
            QPushButton#SyncBtnCancel:hover {
                background: rgba(23, 147, 209, 70);
                border-color: rgba(35, 166, 255, 180);
            }
            QPushButton#SyncBtnConfirm {
                background: rgba(74, 222, 128, 180);
                border: 1px solid rgba(74, 222, 128, 220);
                border-radius: 10px;
                color: #08111d;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#SyncBtnConfirm:hover {
                background: rgba(94, 234, 149, 220);
                border-color: rgba(94, 234, 149, 255);
            }
            QPushButton#SyncBtnConfirm:disabled {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                color: #5f6b7a;
            }
        """.replace("__CHECK_ICON__", _checkbox_check_icon_path()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


# ── Delete helpers ────────────────────────────────────────────────────────────

class _DeleteConfirmDialog(QDialog):
    """Dialog de confirmação estilizado para delete de snapshot."""

    def __init__(self, entry: SnapshotEntry, is_last_root: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("snapshots.delete_confirm_window_title"))
        self.setModal(True)
        self.setFixedSize(520, 300 if is_last_root else 240)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui(entry, is_last_root)
        self._apply_styles()

    def _build_ui(self, entry: SnapshotEntry, is_last_root: bool = False) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("DelHeader")
        header.setFixedHeight(48)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 16, 0)

        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignCenter)
        import qtawesome as qta
        icon.setPixmap(qta.icon("mdi6.delete", color="#ff6666").pixmap(18, 18))
        icon.setStyleSheet("QLabel { background: rgba(200,60,60,40); border-radius: 8px; }")

        lbl = QLabel(tr("snapshots.delete_confirm_header"))
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()



        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        # Body
        body = QFrame()
        body.setObjectName("DelBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 18, 24, 20)
        b_layout.setSpacing(10)

        warn = QLabel(tr("snapshots.delete_warning"))
        warn.setWordWrap(True)
        warn.setFont(QFont("DejaVu Sans Mono", 9))
        warn.setStyleSheet("color: #c8d4e0;")

        root_warn = None
        if is_last_root:
            root_warn = QLabel(tr("snapshots.delete_last_root_warning"))
            root_warn.setWordWrap(True)
            root_warn.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
            root_warn.setStyleSheet(
                "color: #e0a840; background: rgba(224,168,64,0.12); "
                "border-radius: 6px; padding: 8px 10px;"
            )

        pw_note = QLabel(tr("snapshots.delete_password_note"))
        pw_note.setWordWrap(True)
        pw_note.setFont(QFont("DejaVu Sans Mono", 8))
        pw_note.setStyleSheet("color: #5f6b7a;")

        snap_label = QLabel(entry.path.name)
        snap_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        snap_label.setStyleSheet(
            "color: #ff9966; background: rgba(200,60,60,20); "
            "border: 1px solid rgba(200,60,60,60); border-radius: 6px; padding: 4px 10px;"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton(tr("common.cancel"))
        btn_cancel.setObjectName("DelBtnCancel")
        btn_cancel.setFixedWidth(110)
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton(tr("common.delete"))
        btn_confirm.setObjectName("DelBtnConfirm")
        btn_confirm.setFixedWidth(110)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)

        b_layout.addWidget(warn)
        if root_warn is not None:
            b_layout.addWidget(root_warn)
        b_layout.addWidget(snap_label)
        b_layout.addWidget(pw_note)
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
            QPushButton#DelClose {
                background: transparent;
                border: none;
                color: #4a5a6a;
                font-size: 12px;
                border-radius: 6px;
            }
            QPushButton#DelClose:hover {
                background: rgba(200, 60, 60, 60);
                color: #ff8888;
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

    # Drag
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


class _DeleteProgressDialog(QDialog):
    """Loader exibido enquanto o snapshot está sendo removido."""

    def __init__(self, snap_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("snapshots.delete_progress_title"))
        self.setModal(True)
        self.setFixedSize(420, 160)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._dots = 0
        self._spinner_frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self._build_ui(snap_name)
        self._apply_styles()

        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _build_ui(self, snap_name: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("DPHeader")
        header.setFixedHeight(46)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 18, 0)

        import qtawesome as qta
        icon = QLabel()
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.delete", color="#ff6666").pixmap(16, 16))
        icon.setStyleSheet("QLabel { background: rgba(200,60,60,40); border-radius: 7px; }")

        lbl = QLabel(tr("snapshots.delete_progress_title"))
        lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()

        # Body
        body = QFrame()
        body.setObjectName("DPBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 16, 24, 20)
        b_layout.setSpacing(10)

        self.lbl_status = QLabel(tr("snapshots.delete_awaiting_auth"))
        self.lbl_status.setFont(QFont("DejaVu Sans Mono", 10))
        self.lbl_status.setStyleSheet("color: #c8d4e0;")
        self.lbl_status.setAlignment(Qt.AlignCenter)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        status_row.addStretch(1)

        self.lbl_spinner = QLabel("⠋")
        self.lbl_spinner.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        self.lbl_spinner.setStyleSheet("color: #23a6ff;")
        status_row.addWidget(self.lbl_spinner)
        status_row.addWidget(self.lbl_status)
        status_row.addStretch(1)

        snap_lbl = QLabel(snap_name)
        snap_lbl.setFont(QFont("DejaVu Sans Mono", 9))
        snap_lbl.setStyleSheet("color: #6b7a8d;")
        snap_lbl.setAlignment(Qt.AlignCenter)

        # Barra indeterminada slim
        from PySide6.QtWidgets import QProgressBar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # modo indeterminado — pulsa
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setObjectName("DPBar")

        b_layout.addLayout(status_row)
        b_layout.addWidget(snap_lbl)
        b_layout.addSpacing(4)
        b_layout.addWidget(self.progress)

        root.addWidget(header)
        root.addWidget(body, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QFrame#DPHeader {
                background: rgba(30, 10, 10, 255);
                border-bottom: 1px solid rgba(200, 60, 60, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QFrame#DPBody {
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QProgressBar#DPBar {
                background: rgba(31, 92, 255, 20);
                border: none;
                border-radius: 2px;
            }
            QProgressBar#DPBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(31, 92, 255, 220),
                    stop:1 rgba(35, 166, 255, 220)
                );
                border-radius: 2px;
            }
        """)

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % len(self._spinner_frames)
        self.lbl_spinner.setText(self._spinner_frames[self._dots])

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)

    # Drag
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag'):
            self.move(event.globalPosition().toPoint() - self._drag)


class _SyncStatusBadge(QFrame):
    """Pill compacta no cabeçalho do Timeshift — mostra o status da
    sincronização automática e abre o diálogo de configuração ao clicar.
    Ainda sem backend: reflete só o que foi salvo localmente nesta sessão."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SyncStatusBadge")
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(10)

        self._clock_icon = QLabel()
        self._clock_icon.setFixedSize(18, 18)
        self._clock_icon.setPixmap(qta.icon("mdi6.clock-outline", color="#8fd4ff").pixmap(18, 18))

        self._dot = QLabel()
        self._dot.setFixedSize(7, 7)

        self._title_lbl = QLabel(tr("snapshots.sync_badge_title"))
        self._title_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        self._title_lbl.setStyleSheet("color: #ecf4ff;")

        self._sep_lbl = QLabel("·")
        self._sep_lbl.setStyleSheet("color: #6b7a8d;")

        self._detail_lbl = QLabel(tr("snapshots.sync_badge_disabled"))
        self._detail_lbl.setFont(QFont("DejaVu Sans Mono", 10))
        self._detail_lbl.setStyleSheet("color: #8b92a3;")

        self._chevron = QLabel()
        self._chevron.setFixedSize(16, 16)
        self._chevron.setPixmap(qta.icon("mdi6.chevron-right", color="#8b92a3").pixmap(16, 16))

        layout.addWidget(self._clock_icon)
        layout.addWidget(self._dot)
        layout.addWidget(self._title_lbl)
        layout.addWidget(self._sep_lbl)
        layout.addWidget(self._detail_lbl)
        layout.addSpacing(2)
        layout.addWidget(self._chevron)

        self.set_state(enabled=False, next_run=None)

    def _apply_style(self, enabled: bool = False) -> None:
        border = "rgba(52,211,153,90)" if enabled else "rgba(255,255,255,14)"
        border_hover = "rgba(52,211,153,140)" if enabled else "rgba(255,255,255,24)"
        self.setStyleSheet(f"""
            QFrame#SyncStatusBadge {{
                background: rgba(255,255,255,5);
                border: 1px solid {border};
                border-radius: 13px;
            }}
            QFrame#SyncStatusBadge:hover {{
                background: rgba(255,255,255,9);
                border: 1px solid {border_hover};
            }}
            QLabel {{ background: transparent; border: none; }}
        """)

    def set_state(self, enabled: bool, next_run: str | None) -> None:
        dot_color = "#34d399" if enabled else "#6b7a8d"
        self._dot.setStyleSheet(f"background: {dot_color}; border-radius: 3px;")
        if enabled and next_run:
            self._detail_lbl.setText(tr("snapshots.sync_badge_next").format(when=next_run))
        elif enabled:
            self._detail_lbl.setText(tr("snapshots.sync_not_scheduled"))
        else:
            self._detail_lbl.setText(tr("snapshots.sync_badge_disabled"))
        self._apply_style(enabled)

    def retranslate(self) -> None:
        self._title_lbl.setText(tr("snapshots.sync_badge_title"))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _ChipRow(QHBoxLayout):
    """Grupo de chips exclusivos (só um ativo por vez) — mesmo padrão
    visual dos cards de Scope já existentes nesta página."""

    def __init__(self, options: list[tuple[str, str]], active_key: str, on_change) -> None:
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)
        self._buttons: dict[str, QPushButton] = {}
        self._on_change = on_change
        self.active_key = active_key
        for key, label in options:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda _checked=False, k=key: self._select(k))
            self._buttons[key] = btn
            self.addWidget(btn)
        self._refresh_styles()

    def _select(self, key: str) -> None:
        self.active_key = key
        self._refresh_styles()
        self._on_change(key)

    def _refresh_styles(self) -> None:
        for key, btn in self._buttons.items():
            if key == self.active_key:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(35,166,255,26);
                        border: 1px solid rgba(35,166,255,130);
                        border-radius: 8px;
                        color: #8fd4ff;
                        font-family: "DejaVu Sans Mono";
                        font-size: 12px;
                        font-weight: bold;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255,255,255,5);
                        border: 1px solid rgba(255,255,255,14);
                        border-radius: 8px;
                        color: #c8d4e0;
                        font-family: "DejaVu Sans Mono";
                        font-size: 12px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: rgba(255,255,255,9);
                    }
                """)


class _ScheduledSyncDialog(QDialog):
    """Configuração de sincronização automática — SOMENTE UI por enquanto.
    Não escreve nenhuma unit/timer do systemd nem faz nada privilegiado;
    guarda a escolha em memória (`self.result_config`) pra a página exibir
    no badge e pra o backend, quando existir, consumir esse mesmo formato."""

    def __init__(self, current_config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("snapshots.sync_dialog_title"))
        self.setModal(True)
        self.setFixedWidth(800)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.result_config = dict(current_config)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("SyncHeader")
        header.setFixedHeight(48)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 16, 0)

        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.clock-outline", color="#8fd4ff").pixmap(18, 18))
        icon.setStyleSheet("QLabel { background: rgba(35,166,255,40); border-radius: 8px; }")

        lbl = QLabel(tr("snapshots.sync_dialog_title"))
        lbl.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.reject()

        h_layout.addWidget(icon)
        h_layout.addSpacing(10)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        # ── Corpo ───────────────────────────────────────────────────
        body = QFrame()
        body.setObjectName("SyncBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(36, 32, 36, 32)
        b_layout.setSpacing(26)

        # Toggle ativar/desativar
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_lbl = QLabel(tr("snapshots.sync_dialog_title").upper())
        toggle_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        toggle_lbl.setStyleSheet("color: #8b92a3; letter-spacing: 1px;")
        toggle_row.addWidget(toggle_lbl)
        toggle_row.addStretch()

        self.btn_toggle = QPushButton(
            tr("snapshots.sync_enabled") if self.result_config.get("enabled") else tr("snapshots.sync_disabled")
        )
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setFixedSize(120, 36)
        self.btn_toggle.clicked.connect(self._toggle_enabled)
        toggle_row.addWidget(self.btn_toggle)
        b_layout.addLayout(toggle_row)

        # Frequência
        freq_lbl = QLabel(tr("snapshots.sync_frequency_label"))
        freq_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        freq_lbl.setStyleSheet("color: #8b92a3; letter-spacing: 1px;")
        b_layout.addWidget(freq_lbl)

        self._freq_row = _ChipRow(
            [
                ("daily", tr("snapshots.sync_freq_daily")),
                ("weekly", tr("snapshots.sync_freq_weekly")),
                ("custom", tr("snapshots.sync_freq_custom")),
            ],
            self.result_config.get("frequency", "daily"),
            self._on_frequency_changed,
        )
        b_layout.addLayout(self._freq_row)

        # Dia da semana — só aparece com Semanal
        self._weekday_container = QWidget()
        weekday_layout = QVBoxLayout(self._weekday_container)
        weekday_layout.setContentsMargins(0, 4, 0, 0)
        weekday_layout.setSpacing(10)

        weekday_lbl = QLabel(tr("snapshots.sync_weekday_label"))
        weekday_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        weekday_lbl.setStyleSheet("color: #8b92a3; letter-spacing: 1px;")
        weekday_layout.addWidget(weekday_lbl)

        weekday_options = [
            ("Mon", tr("snapshots.sync_weekday_mon")),
            ("Tue", tr("snapshots.sync_weekday_tue")),
            ("Wed", tr("snapshots.sync_weekday_wed")),
            ("Thu", tr("snapshots.sync_weekday_thu")),
            ("Fri", tr("snapshots.sync_weekday_fri")),
            ("Sat", tr("snapshots.sync_weekday_sat")),
            ("Sun", tr("snapshots.sync_weekday_sun")),
        ]
        self._weekday_row = _ChipRow(
            weekday_options,
            self.result_config.get("weekday", "Mon"),
            lambda key: (self.result_config.__setitem__("weekday", key), self._refresh_status_card()),
        )
        weekday_layout.addLayout(self._weekday_row)
        b_layout.addWidget(self._weekday_container)

        # Horário — não se aplica ao modo Personalizada (o horário já
        # vai embutido na expressão que o usuário digitar)
        self._time_container = QWidget()
        time_layout = QVBoxLayout(self._time_container)
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(10)

        time_lbl = QLabel(tr("snapshots.sync_time_label"))
        time_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        time_lbl.setStyleSheet("color: #8b92a3; letter-spacing: 1px; margin-top: 4px;")
        time_layout.addWidget(time_lbl)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        saved_time = self.result_config.get("time", "03:00")
        h, m = (int(x) for x in saved_time.split(":"))
        self.time_edit.setTime(QTime(h, m))
        self.time_edit.setFixedHeight(40)
        self.time_edit.setStyleSheet("""
            QTimeEdit {
                background: rgba(255,255,255,5);
                border: 1px solid rgba(255,255,255,14);
                border-radius: 8px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 13px;
                font-weight: bold;
                padding: 0 12px;
            }
            QTimeEdit::up-button, QTimeEdit::down-button {
                background: transparent;
                border: none;
                width: 18px;
            }
            QTimeEdit::up-arrow, QTimeEdit::down-arrow {
                width: 8px;
                height: 8px;
            }
        """)
        self.time_edit.timeChanged.connect(
            lambda t: (self.result_config.__setitem__("time", t.toString("HH:mm")), self._refresh_status_card())
        )
        time_layout.addWidget(self.time_edit)
        b_layout.addWidget(self._time_container)

        # Expressão personalizada — só aparece com Personalizada
        self._custom_container = QWidget()
        custom_layout = QVBoxLayout(self._custom_container)
        custom_layout.setContentsMargins(0, 4, 0, 0)
        custom_layout.setSpacing(8)

        custom_lbl = QLabel(tr("snapshots.sync_custom_label"))
        custom_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        custom_lbl.setStyleSheet("color: #8b92a3; letter-spacing: 1px;")
        custom_layout.addWidget(custom_lbl)

        self.custom_edit = QLineEdit(self.result_config.get("custom_expression", ""))
        self.custom_edit.setPlaceholderText("*-*-* 03:00:00")
        self.custom_edit.setFixedHeight(40)
        self.custom_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,5);
                border: 1px solid rgba(255,255,255,14);
                border-radius: 8px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 12px;
                padding: 0 12px;
            }
        """)
        self.custom_edit.textChanged.connect(
            lambda text: (self.result_config.__setitem__("custom_expression", text), self._refresh_status_card())
        )
        custom_layout.addWidget(self.custom_edit)

        custom_hint = QLabel(tr("snapshots.sync_custom_hint"))
        custom_hint.setFont(QFont("DejaVu Sans Mono", 8))
        custom_hint.setStyleSheet("color: #6b7a8d;")
        custom_hint.setWordWrap(True)
        custom_layout.addWidget(custom_hint)

        b_layout.addWidget(self._custom_container)

        self._update_frequency_visibility(self.result_config.get("frequency", "daily"))

        # Escopo
        scope_lbl = QLabel(tr("snapshots.sync_scope_label"))
        scope_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        scope_lbl.setStyleSheet("color: #8b92a3; letter-spacing: 1px; margin-top: 4px;")
        b_layout.addWidget(scope_lbl)

        self._scope_row = _ChipRow(
            [
                ("root", "ROOT"),
                ("home", "HOME"),
                ("both", "ROOT+HOME"),
            ],
            self.result_config.get("scope", "both"),
            lambda key: self.result_config.__setitem__("scope", key),
        )
        b_layout.addLayout(self._scope_row)

        # Destinos — antes o agendamento só via UM destino (o que estava
        # selecionado na tela principal no momento em que o diálogo abria).
        # Agora é uma lista: cada disco marcado aqui entra na sincronização
        # automática, independente de qual está selecionado na tela.
        dest_lbl = QLabel(tr("snapshots.sync_destinations_label"))
        dest_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        dest_lbl.setStyleSheet("color: #8b92a3; letter-spacing: 1px; margin-top: 4px;")
        b_layout.addWidget(dest_lbl)

        selected_mountpoints = set(self.result_config.get("destination_mountpoints", []))
        self._destination_checks: dict[str, QCheckBox] = {}
        self._destination_rows: dict[str, QFrame] = {}
        available_destinations = list_backup_destinations()

        dest_container = QVBoxLayout()
        dest_container.setSpacing(8)

        if not available_destinations:
            none_lbl = QLabel(tr("snapshots.sync_no_destinations_found"))
            none_lbl.setFont(QFont("DejaVu Sans Mono", 9))
            none_lbl.setStyleSheet("color: #6b7a8d;")
            dest_container.addWidget(none_lbl)
        else:
            for dest in available_destinations:
                row = QFrame()
                row.setObjectName("DestRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(14, 10, 14, 10)
                row_layout.setSpacing(12)

                cb = QCheckBox()
                cb.setObjectName("SyncCheckbox")
                cb.setFixedSize(18, 18)
                cb.setCursor(Qt.PointingHandCursor)
                cb.setChecked(dest.mountpoint in selected_mountpoints)

                label_lbl = QLabel(f"{dest.label}  ·  {dest.mountpoint}  ·  {format_gb(dest.free_gb)} livre")
                label_lbl.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
                label_lbl.setStyleSheet("color: #ecf4ff;")

                row_layout.addWidget(cb)
                row_layout.addWidget(label_lbl, 1)

                cb.toggled.connect(self._on_destination_toggle)
                self._destination_checks[dest.mountpoint] = cb
                self._destination_rows[dest.mountpoint] = row
                self._update_dest_row_style(row, cb.isChecked())
                dest_container.addWidget(row)

        b_layout.addLayout(dest_container)

        # Status (última/próxima execução) — sem backend ainda, mostra
        # sempre o estado "nunca executado" nesta rodada
        status_card = QFrame()
        status_card.setObjectName("SyncStatusCard")
        status_card.setStyleSheet("""
            QFrame#SyncStatusCard {
                background: rgba(255,255,255,4);
                border: 1px solid rgba(255,255,255,8);
                border-radius: 10px;
            }
            QFrame#SyncStatusCard QLabel {
                background: transparent;
                border: none;
            }
        """)
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(22, 20, 22, 20)

        last_block = QVBoxLayout()
        last_block.setContentsMargins(0, 0, 0, 0)
        last_block.setSpacing(6)
        last_caption = QLabel(tr("snapshots.sync_last_run_label"))
        last_caption.setFont(QFont("DejaVu Sans Mono", 10))
        last_caption.setStyleSheet("color: #8b92a3;")
        self.last_value = QLabel(tr("snapshots.sync_never_run"))
        self.last_value.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        self.last_value.setStyleSheet("color: #ecf4ff;")
        last_block.addWidget(last_caption)
        last_block.addWidget(self.last_value)
        status_layout.addLayout(last_block)
        status_layout.addStretch()

        next_block = QVBoxLayout()
        next_block.setContentsMargins(0, 0, 0, 0)
        next_block.setSpacing(6)
        next_caption = QLabel(tr("snapshots.sync_next_run_label"))
        next_caption.setFont(QFont("DejaVu Sans Mono", 10))
        next_caption.setStyleSheet("color: #8b92a3;")
        self.next_value = QLabel(tr("snapshots.sync_not_scheduled"))
        self.next_value.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        self.next_value.setStyleSheet("color: #ecf4ff;")
        next_block.addWidget(next_caption)
        next_block.addWidget(self.next_value)
        status_layout.addLayout(next_block)

        b_layout.addWidget(status_card)
        self._refresh_status_card()

        note = QLabel(tr("snapshots.sync_backend_note"))
        note.setWordWrap(True)
        note.setFont(QFont("DejaVu Sans Mono", 9))
        note.setStyleSheet("color: #6b7a8d;")
        b_layout.addWidget(note)

        b_layout.addStretch()

        # Botões
        btn_final_row = QHBoxLayout()
        btn_final_row.setSpacing(10)

        self.btn_cancel_schedule = QPushButton(tr("snapshots.sync_cancel_button"))
        self.btn_cancel_schedule.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_schedule.setFixedHeight(44)
        self.btn_cancel_schedule.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 10px;
                color: #ecf4ff;
                font-family: "DejaVu Sans Mono";
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255,120,120,40);
                border-color: rgba(255,120,120,140);
            }
            QPushButton:disabled {
                color: #5f6b7a;
            }
        """)
        self.btn_cancel_schedule.clicked.connect(self._on_cancel_schedule)
        self.btn_cancel_schedule.setEnabled(self.result_config.get("enabled", False))

        self.btn_save = QPushButton(tr("snapshots.sync_save_button"))
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setFixedHeight(44)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: #23a6ff;
                border: none;
                border-radius: 10px;
                color: #04203a;
                font-family: "DejaVu Sans Mono";
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #4fb8ff;
            }
            QPushButton:disabled {
                background: rgba(35,166,255,80);
                color: rgba(4,32,58,150);
            }
        """)
        self.btn_save.clicked.connect(self._on_save)

        btn_final_row.addWidget(self.btn_cancel_schedule, 1)
        btn_final_row.addWidget(self.btn_save, 1)
        b_layout.addLayout(btn_final_row)

        root.addWidget(header)
        root.addWidget(body, 1)

    def _refresh_status_card(self) -> None:
        from core.snapshots import scheduler
        from datetime import datetime

        status = scheduler.load_schedule_status()
        last_run = status.get("last_run")
        if last_run:
            try:
                when = datetime.fromisoformat(last_run).strftime("%d/%m %H:%M")
            except ValueError:
                when = last_run
            result_key = {
                "success": "snapshots.sync_result_success",
                "failed": "snapshots.sync_result_failed",
                "skipped": "snapshots.sync_result_skipped",
                "nothing_to_sync": "snapshots.sync_result_nothing",
            }.get(status.get("last_result"), status.get("last_result") or "")
            result_txt = tr(result_key) if result_key else "?"
            self.last_value.setText(tr("snapshots.sync_last_run_value").format(when=when, result=result_txt))
            color = {
                "success": "#9bf0bd",
                "failed": "#ff8888",
                "skipped": "#e0a840",
                "nothing_to_sync": "#c8d4e0",
            }.get(status.get("last_result"), "#ecf4ff")
            self.last_value.setStyleSheet(f"color: {color};")
        else:
            self.last_value.setText(tr("snapshots.sync_never_run"))
            self.last_value.setStyleSheet("color: #ecf4ff;")

        next_run = scheduler.next_run_display(self.result_config) if self.result_config.get("enabled") else None
        self.next_value.setText(next_run if next_run else tr("snapshots.sync_not_scheduled"))

    def _update_dest_row_style(self, row: QFrame, checked: bool) -> None:
        if checked:
            row.setStyleSheet("""
                QFrame#DestRow {
                    background: rgba(59,130,246,56);
                    border: 1px solid rgba(99,140,255,130);
                    border-radius: 10px;
                }
                QFrame#DestRow QLabel { background: transparent; border: none; }
            """)
        else:
            row.setStyleSheet("""
                QFrame#DestRow {
                    background: rgba(255,255,255,4);
                    border: 1px solid rgba(255,255,255,14);
                    border-radius: 10px;
                }
                QFrame#DestRow QLabel { background: transparent; border: none; color: #c8d4e0; }
            """)

    def _on_destination_toggle(self) -> None:
        for mountpoint, cb in self._destination_checks.items():
            self._update_dest_row_style(self._destination_rows[mountpoint], cb.isChecked())
        self.result_config["destination_mountpoints"] = [
            mp for mp, cb in self._destination_checks.items() if cb.isChecked()
        ]
        self._refresh_status_card()

    def _on_frequency_changed(self, key: str) -> None:
        self.result_config["frequency"] = key
        self._update_frequency_visibility(key)
        self._refresh_status_card()

    def _update_frequency_visibility(self, freq: str) -> None:
        self._weekday_container.setVisible(freq == "weekly")
        self._custom_container.setVisible(freq == "custom")
        self._time_container.setVisible(freq in ("daily", "weekly"))

    def _on_save(self) -> None:
        if not self.result_config.get("destination_mountpoints"):
            _show_error("Carbonara", tr("snapshots.sync_no_destination"), parent=self)
            return

        from core.snapshots import scheduler
        scheduler.save_schedule_config(self.result_config)

        args_json = json.dumps({"config": self.result_config})
        cmd = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "scheduler.install",
            args_json,
        ]

        self.btn_save.setEnabled(False)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception as exc:
            self.btn_save.setEnabled(True)
            _show_error("Carbonara", tr("snapshots.sync_install_failed").format(msg=str(exc)), parent=self)
            return
        self.btn_save.setEnabled(True)

        if result.returncode == 126:
            return  # pkexec cancelado na autenticação — deixa o diálogo aberto pra tentar de novo
        if result.returncode != 0:
            err = result.stderr.strip() or f"exit code {result.returncode}"
            _show_error("Carbonara", tr("snapshots.sync_install_failed").format(msg=err), parent=self)
            return

        self.accept()

    def _on_cancel_schedule(self) -> None:
        from core.snapshots import scheduler
        self.result_config["enabled"] = False
        scheduler.save_schedule_config(self.result_config)

        args_json = json.dumps({"config": self.result_config})
        cmd = [
            "pkexec",
            "/usr/local/bin/carbonara-helper",
            os.environ.get("DISPLAY", ""),
            os.environ.get("XAUTHORITY", ""),
            "scheduler.install",
            args_json,
        ]

        self.btn_cancel_schedule.setEnabled(False)
        self.btn_save.setEnabled(False)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception as exc:
            self.btn_cancel_schedule.setEnabled(True)
            self.btn_save.setEnabled(True)
            _show_error("Carbonara", tr("snapshots.sync_install_failed").format(msg=str(exc)), parent=self)
            return
        self.btn_save.setEnabled(True)

        if result.returncode == 126:
            self.btn_cancel_schedule.setEnabled(True)
            return  # pkexec cancelado na autenticação — deixa o diálogo aberto pra tentar de novo
        if result.returncode != 0:
            self.btn_cancel_schedule.setEnabled(True)
            err = result.stderr.strip() or f"exit code {result.returncode}"
            _show_error("Carbonara", tr("snapshots.sync_install_failed").format(msg=err), parent=self)
            return

        self.accept()

    def _toggle_enabled(self) -> None:
        enabled = not self.result_config.get("enabled", False)
        self.result_config["enabled"] = enabled
        self.btn_toggle.setText(tr("snapshots.sync_enabled") if enabled else tr("snapshots.sync_disabled"))
        self._apply_toggle_style()
        self._refresh_status_card()
        self.btn_cancel_schedule.setEnabled(enabled)

    def _apply_toggle_style(self) -> None:
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background: rgba(52,211,153,26);
                border: 1px solid rgba(52,211,153,130);
                border-radius: 8px;
                color: #9bf0bd;
                font-family: "DejaVu Sans Mono";
                font-size: 10px;
                font-weight: bold;
            }
        """ if self.result_config.get("enabled") else """
            QPushButton {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,16);
                border-radius: 8px;
                color: #8b92a3;
                font-family: "DejaVu Sans Mono";
                font-size: 10px;
                font-weight: bold;
            }
        """)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog { background: #14151c; border-radius: 14px; }
            QFrame#SyncHeader {
                background: #191a22;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
                border-bottom: 1px solid rgba(255,255,255,10);
            }
            QFrame#SyncBody { background: transparent; }
            QLabel { background: transparent; border: none; }
            QCheckBox#SyncCheckbox {
                background: transparent;
                spacing: 0px;
            }
            QCheckBox#SyncCheckbox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,30);
            }
            QCheckBox#SyncCheckbox::indicator:checked {
                background: rgba(59,130,246,220);
                border: 1px solid rgba(99,140,255,255);
                image: url(__CHECK_ICON__);
            }
        """.replace("__CHECK_ICON__", _checkbox_check_icon_path()))
        self._apply_toggle_style()


class _CreateSnapshotConfirmDialog(QDialog):
    """Confirmação antes de criar um snapshot novo — mostra o escopo
    selecionado no momento (ROOT/HOME/ROOT+HOME) pra evitar cliques
    acidentais no escopo errado. Mesmo chrome dos outros diálogos de
    confirmação desta página (_DeleteConfirmDialog etc)."""

    _SCOPE_LABEL_KEYS = {
        "root": "snapshots.scope_root_title",
        "home": "snapshots.scope_home_title",
        "both": "snapshots.scope_both_title",
    }
    _SCOPE_DESC_KEYS = {
        "root": "snapshots.create_confirm_desc_root",
        "home": "snapshots.create_confirm_desc_home",
        "both": "snapshots.create_confirm_desc_both",
    }

    def __init__(self, scope: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("snapshots.create_confirm_title"))
        self.setModal(True)
        self.setFixedWidth(535)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("CreateSnapHeader")
        header.setFixedHeight(48)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 16, 0)

        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon(CREATE_GLYPH, color="#9bf0bd").pixmap(18, 18))
        icon.setStyleSheet("QLabel { background: rgba(52,211,153,40); border-radius: 8px; }")

        lbl = QLabel(tr("snapshots.create_confirm_title"))
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
        body.setObjectName("CreateSnapBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(24, 20, 24, 20)
        b_layout.setSpacing(14)

        intro = QLabel(tr("snapshots.create_confirm_body"))
        intro.setFont(QFont("DejaVu Sans Mono", 10))
        intro.setStyleSheet("color: #c8d4e0;")
        b_layout.addWidget(intro)

        scope_badge = QFrame()
        scope_badge.setObjectName("CreateSnapScopeBadge")
        scope_badge.setFixedHeight(40)
        scope_badge.setStyleSheet("""
            QFrame#CreateSnapScopeBadge {
                background: rgba(59,130,246,56);
                border: 1px solid rgba(99,140,255,130);
                border-radius: 10px;
            }
            QFrame#CreateSnapScopeBadge QLabel {
                background: transparent;
                border: none;
            }
        """)
        scope_layout = QVBoxLayout(scope_badge)
        scope_layout.setContentsMargins(12, 0, 12, 0)
        scope_label = QLabel(tr(self._SCOPE_LABEL_KEYS.get(scope, "snapshots.scope_both_title")))
        scope_label.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        scope_label.setStyleSheet("color: #ffffff;")
        scope_label.setAlignment(Qt.AlignCenter)
        scope_layout.addWidget(scope_label)
        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(0, 0, 0, 0)
        scope_row.addStretch(1)
        scope_row.addWidget(scope_badge, 4)
        scope_row.addStretch(1)
        b_layout.addSpacing(2)
        b_layout.addLayout(scope_row)
        b_layout.addSpacing(2)

        desc_text = tr(self._SCOPE_DESC_KEYS.get(scope, "snapshots.create_confirm_desc_both"))
        desc = QLabel(desc_text)
        desc_font = QFont("DejaVu Sans Mono", 9)
        desc.setFont(desc_font)
        desc.setStyleSheet("color: #8b92a3; line-height: 170%;")
        desc.setWordWrap(True)
        desc_width = 535 - 24 - 24
        desc_rect = QFontMetrics(desc_font).boundingRect(QRect(0, 0, desc_width, 0), Qt.TextWordWrap, desc_text)
        desc.setFixedHeight(desc_rect.height() + 26)
        b_layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton(tr("common.cancel"))
        btn_cancel.setObjectName("CreateSnapBtnCancel")
        btn_cancel.setFixedHeight(40)
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton(tr("snapshots.btn_create_snapshot"))
        btn_confirm.setFixedHeight(40)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background: #34d399;
                border: none;
                border-radius: 9px;
                color: #04291c;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #4fe0ac;
            }
        """)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addWidget(btn_cancel, 1)
        btn_row.addWidget(btn_confirm, 1)
        b_layout.addLayout(btn_row)

        self.setStyleSheet("""
            QDialog { background: #14151c; border-radius: 14px; }
            QFrame#CreateSnapHeader {
                background: rgba(52,211,153,20);
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
                border-bottom: 1px solid rgba(52,211,153,60);
            }
            QFrame#CreateSnapBody { background: transparent; }
            QPushButton#CreateSnapBtnCancel {
                background: rgba(255,255,255,6);
                border: 1px solid rgba(255,255,255,16);
                border-radius: 9px;
                color: #c8d4e0;
                font-family: "DejaVu Sans Mono";
                font-size: 11px;
                font-weight: bold;
            }
            QLabel { background: transparent; border: none; }
        """)

        root.addWidget(header)
        root.addWidget(body)


class _DeleteWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, snapshot_path: Path, parent=None):
        super().__init__(parent)
        self._path = snapshot_path

    def run(self) -> None:
        try:
            kind_base = self._path.parent
            link = kind_base / "latest"

            # Verifica se este snapshot é o apontado pelo latest
            is_latest = False
            try:
                if link.is_symlink():
                    resolved = (kind_base / link.readlink()).resolve()
                    is_latest = resolved == self._path.resolve()
            except Exception:
                pass

            # Calcula qual será o novo latest antes de deletar
            new_latest: Path | None = None
            if is_latest:
                candidates = sorted(
                    [p for p in kind_base.iterdir()
                     if p.is_dir() and p.name != "latest" and p != self._path],
                    key=lambda p: p.name,
                )
                new_latest = candidates[-1] if candidates else None

            args_json = json.dumps({
                "target": str(self._path),
                "link": str(link),
                "new_latest": str(new_latest) if new_latest else None,
            })

            result = subprocess.run(
                [
                    "pkexec",
                    "/usr/local/bin/carbonara-helper",
                    os.environ.get("DISPLAY", ""),
                    os.environ.get("XAUTHORITY", ""),
                    "backup.delete_snapshot",
                    args_json,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                err = result.stderr.strip() or f"exit code {result.returncode}"
                if result.returncode == 126 or "dismissed" in err.lower():
                    err = tr("snapshots.delete_cancelled")
                self.failed.emit(err)
                return

            self.finished_ok.emit(tr("snapshots.delete_success").format(name=self._path.name))

        except Exception as exc:
            self.failed.emit(str(exc))
