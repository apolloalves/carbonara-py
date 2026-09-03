from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QFont, QPainter, QPen, QColor, QKeyEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFrame,
    QDialog,
)

from core.system.doctor import run_full_checkup, DoctorReport, Finding
from core.operation_manager import OperationManager

# Paleta alinhada ao main_window.py / disks_page.py (estilo SaaS)
BG = "#0a0b0f"
TEXT = "#e4e7ec"
MUTED = "#8b92a3"
FAINT = "#6b7280"

ACCENT_BLUE = "#3b82f6"
ACCENT_BLUE_LIGHT = "#60a5fa"
ACCENT_PURPLE = "#8b5cf6"
ACCENT_GREEN = "#34d399"
ACCENT_AMBER = "#fbbf24"
ACCENT_RED = "#f87171"

FONT_FAMILY = "DejaVu Sans Mono"

LEVEL_COLOR = {"critical": ACCENT_RED, "warning": ACCENT_AMBER, "ok": ACCENT_GREEN}

# Frase em linguagem simples pra cada tipo de achado — o detail técnico
# do core (contagem, nome de arquivo) fica só no título; aqui explica o
# que aquilo significa na prática, sem jargão.
FRIENDLY_DETAIL = {
    "failed_services": "Um serviço parou de rodar e não voltou sozinho — vale checar o motivo.",
    "pacnew": "Configs de pacotes foram atualizadas — vale revisar o que mudou.",
    "orphans": "Pacotes que nada mais usa, ocupando espaço à toa.",
    "orphan_kernels": "Kernel instalado que você não está usando no momento.",
    "log_dirs": "Pastas que alguns programas esperam encontrar e não existem.",
    "empty_libs": "Um update foi interrompido no meio e deixou biblioteca(s) corrompida(s).",
    "critical_timers": "Uma automação que evita quebras parou de rodar.",
    "volumes": "Um disco pode ter erro de sistema de arquivos.",
    "smart": "Um disco está reportando problema de saúde física.",
    "raid": "O array RAID está funcionando com um disco a menos.",
}

# Cada achado "fixable" mapeia pra uma ação registrada no ACTIONS do
# carbonara-helper. Achados sem entrada aqui simplesmente não mostram
# botão (controlado por Finding.fixable no doctor.py).
FINDING_ACTION_MAP = {
    "orphans": ("doctor.cleanup", {"categories": ["orphans"]}),
    "log_dirs": ("doctor.fix_log_dirs", {}),
    "volumes": ("doctor.fsck_repair", {}),
    "empty_libs": ("doctor.fix_empty_libs", {}),
}

CARD_STYLE = """
    QFrame { border: 1px solid rgba(255,255,255,12); border-radius: 14px; background: rgba(255,255,255,4); }
    QLabel { background: transparent; border: none; }
"""


def _rgba(hex_color: str, alpha: int) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r}, {g}, {b}, {alpha}"


class HealthRing(QWidget):
    """Anel de saúde 0-100, cor semântica conforme a faixa."""

    def __init__(self, score: int = 100, size: int = 88, parent=None):
        super().__init__(parent)
        self._score = score
        self._size = size
        self.setFixedSize(size, size)

    def set_score(self, score: int) -> None:
        self._score = score
        self.update()

    def _color(self) -> QColor:
        if self._score >= 80:
            return QColor(ACCENT_GREEN)
        if self._score >= 50:
            return QColor(ACCENT_AMBER)
        return QColor(ACCENT_RED)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pad = 7
        rect = QRectF(pad, pad, self._size - 2 * pad, self._size - 2 * pad)
        color = self._color()

        bg_pen = QPen(QColor(255, 255, 255, 20))
        bg_pen.setWidth(9)
        bg_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        fg_pen = QPen(color)
        fg_pen.setWidth(9)
        fg_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(fg_pen)
        span = int(360 * 16 * (self._score / 100))
        painter.drawArc(rect, 90 * 16, -span)

        number_rect = QRectF(0, self._size * 0.24, self._size, self._size * 0.4)
        painter.setPen(QColor(TEXT))
        painter.setFont(QFont(FONT_FAMILY, int(self._size * 0.26), QFont.Bold))
        painter.drawText(number_rect, Qt.AlignCenter, str(self._score))

        label_rect = QRectF(0, self._size * 0.58, self._size, self._size * 0.16)
        painter.setPen(color)
        label_font = QFont(FONT_FAMILY, int(self._size * 0.09), QFont.Bold)
        label_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        painter.setFont(label_font)
        painter.drawText(label_rect, Qt.AlignCenter, "SCORE")


class FindingRow(QFrame):
    """Achado com borda colorida à esquerda (severidade) + ícone + texto
    + ação — versão com mais peso visual que a bolinha discreta anterior,
    pra ficar óbvio o que precisa de atenção."""

    LEVEL_ICON = {"critical": "mdi6.alert-octagon-outline", "warning": "mdi6.file-multiple-outline", "ok": "mdi6.check-circle-outline"}
    LEVEL_BG = {"critical": "#1a0e0e", "warning": "#17140a", "ok": "#0d0e13"}

    def __init__(self, finding: Finding, is_last: bool = False, on_action=None, on_view=None, parent=None):
        super().__init__(parent)
        color = LEVEL_COLOR[finding.level]
        bg = self.LEVEL_BG[finding.level]
        margin_bottom = "0px" if is_last else "1px"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: none; border-left: 3px solid {color}; "
            f"margin-bottom: {margin_bottom}; }} QLabel {{ background: transparent; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        icon = QLabel()
        icon.setPixmap(qta.icon(self.LEVEL_ICON[finding.level], color=color).pixmap(18, 18))
        layout.addWidget(icon)

        text_block = QVBoxLayout()
        text_block.setSpacing(2)
        title = QLabel(finding.title)
        title.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT};")
        detail = QLabel(FRIENDLY_DETAIL.get(finding.id, finding.detail))
        detail.setFont(QFont(FONT_FAMILY, 10))
        detail.setStyleSheet(f"color: {color if finding.level == 'critical' else MUTED};")
        detail.setWordWrap(True)
        text_block.addWidget(title)
        text_block.addWidget(detail)
        layout.addLayout(text_block, 1)

        if finding.fixable and finding.level != "ok":
            btn = QPushButton("Revisar")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid rgba({_rgba(color, 100)});
                    color: {color};
                    border-radius: 7px;
                    padding: 6px 14px;
                    font-family: "{FONT_FAMILY}";
                    font-size: 11px;
                }}
                QPushButton:hover {{ background: rgba({_rgba(color, 20)}); }}
                QPushButton:disabled {{ opacity: 0.5; }}
            """)
            if on_action:
                btn.clicked.connect(lambda: on_action(finding.id, btn))
            layout.addWidget(btn)
        elif finding.extra and finding.level != "ok":
            # Achados que só têm dado auxiliar pra mostrar (ex: lista de
            # arquivos pacnew/pacsave) — botão neutro, não colorido como
            # "Revisar", porque não corrige nada sozinho, só exibe.
            btn = QPushButton("Ver arquivos")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid rgba(255,255,255,40);
                    color: {MUTED};
                    border-radius: 7px;
                    padding: 6px 14px;
                    font-family: "{FONT_FAMILY}";
                    font-size: 11px;
                }}
                QPushButton:hover {{ background: rgba(255,255,255,14); color: {TEXT}; }}
            """)
            if on_view:
                btn.clicked.connect(lambda: on_view(finding))
            layout.addWidget(btn)


class ActionCard(QFrame):
    """Card pequeno usado na grade 'Ações rápidas' do rodapé da coluna
    principal (Limpeza, Volumes, Automação, Watchlist)."""

    def __init__(self, icon_name: str, title: str, subtitle: str,
                 action_label: str | None = None, status: str | None = None,
                 status_color: str = ACCENT_GREEN, on_action=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(qta.icon(icon_name, color=MUTED).pixmap(14, 14))
        top.addWidget(icon)
        top.addStretch()

        if action_label:
            self.btn = QPushButton(action_label)
            self.btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,255,255,8);
                    border: none;
                    color: {TEXT};
                    border-radius: 7px;
                    padding: 4px 9px;
                    font-family: "{FONT_FAMILY}";
                    font-size: 10px;
                }}
                QPushButton:hover {{ background: rgba(255,255,255,14); }}
                QPushButton:disabled {{ color: {FAINT}; }}
            """)
            if on_action:
                self.btn.clicked.connect(lambda: on_action(self.btn))
            top.addWidget(self.btn)
        elif status:
            status_lbl = QLabel(status)
            status_lbl.setFont(QFont(FONT_FAMILY, 10))
            status_lbl.setStyleSheet(f"color: {status_color};")
            top.addWidget(status_lbl)

        layout.addLayout(top)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT};")
        layout.addWidget(title_lbl)

        sub = QLabel(subtitle)
        sub.setFont(QFont(FONT_FAMILY, 10))
        sub.setStyleSheet(f"color: {FAINT};")
        layout.addWidget(sub)


class VitalCard(QFrame):
    """Card da fileira 'Vitals do sistema' — label pequeno em cima, valor
    grande embaixo, igual um stat card de dashboard."""

    def __init__(self, label: str, value: str, value_color: str = TEXT, parent=None):
        super().__init__(parent)
        self.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        label_lbl = QLabel(label)
        label_lbl.setFont(QFont(FONT_FAMILY, 9, QFont.Bold))
        label_lbl.setStyleSheet(f"color: {FAINT}; letter-spacing: 0.5px;")
        layout.addWidget(label_lbl)

        value_lbl = QLabel(value)
        value_lbl.setFont(QFont(FONT_FAMILY, 14, QFont.Bold))
        value_lbl.setStyleSheet(f"color: {value_color};")
        layout.addWidget(value_lbl)


class _CloseLabel(QLabel):
    """'X' de fechar clicável — cópia exata do padrão usado em eggs_page.py."""

    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setFixedSize(24, 24)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QLabel { color: #9aa6b2; font-size: 13px; border-radius: 6px; }"
            "QLabel:hover { background: rgba(200,60,60,60); color: #ff8888; }"
        )


class FindingDetailDialog(QDialog):
    """Diálogo só de leitura pra achados que não têm correção automática
    (ex: pacnew/pacsave) — mostra a lista de arquivos e orienta o
    próximo passo manual, sem tentar mexer em nada sozinho."""

    def __init__(self, finding: Finding, guidance: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(finding.title)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(600)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("ResHeader")
        header.setFixedHeight(46)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 14, 0)

        icon = QLabel()
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.file-multiple-outline", color=ACCENT_AMBER).pixmap(16, 16))
        icon.setStyleSheet("QLabel { background: rgba(251,191,36,40); border-radius: 7px; }")

        lbl = QLabel(finding.title)
        lbl.setFont(QFont(FONT_FAMILY, 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.accept()

        h_layout.addWidget(icon)
        h_layout.addSpacing(8)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        body = QFrame()
        body.setObjectName("ResBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(20, 16, 20, 18)
        b_layout.setSpacing(12)

        if guidance:
            guidance_lbl = QLabel(guidance)
            guidance_lbl.setFont(QFont(FONT_FAMILY, 9))
            guidance_lbl.setStyleSheet(f"color: {MUTED};")
            guidance_lbl.setWordWrap(True)
            b_layout.addWidget(guidance_lbl)

        files_lbl = QLabel(finding.extra or "(nenhum arquivo)")
        files_lbl.setFont(QFont(FONT_FAMILY, 9))
        files_lbl.setStyleSheet(f"color: {TEXT}; background: #0d0e13; border-radius: 8px; padding: 10px;")
        files_lbl.setWordWrap(True)
        files_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_layout.addWidget(files_lbl)

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("ResBtnOk")
        btn_ok.setFixedWidth(90)
        btn_ok.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body)

        self.setStyleSheet(f"""
            QFrame#ResHeader {{
                background: rgba(251,191,36, 35);
                border-bottom: 1px solid rgba(251,191,36, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
            QFrame#ResBody {{
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }}
            QPushButton#ResBtnOk {{
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba(251,191,36, 120);
                border-radius: 8px; color: #ecf4ff;
                font-family: "{FONT_FAMILY}";
                font-size: 11px; padding: 5px 0;
            }}
            QPushButton#ResBtnOk:hover {{
                background: rgba(251,191,36, 40);
                border-color: rgba(251,191,36, 200);
            }}
        """)
        self.adjustSize()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(event.globalPosition().toPoint() - self._drag)


# Orientação de próximo passo manual por achado — só pra achados sem
# correção automática (view-only), explicando o comando certo a rodar.
FINDING_GUIDANCE = {
    "pacnew": (
        "Isso não é corrigido automaticamente — mesclar configs é uma decisão "
        "sua. No terminal, rode:\n\n  sudo pacdiff\n\ne revise arquivo por "
        "arquivo (aceitar a versão nova, manter a sua, ou descartar)."
    ),
}


class ActionResultDialog(QDialog):
    """Clone exato do padrão _ErrorDialog/_show_error de eggs_page.py
    (header com ícone+título+X, corpo com mensagem+OK) — mesmo componente
    usado em todo o app pra erro, só que aqui com variante verde quando
    a ação teve sucesso."""

    def __init__(self, success: bool, message: str, detail: str = "", parent=None):
        super().__init__(parent)
        title = "Ação concluída" if success else "Ação falhou"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(640)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        accent = "80,200,140" if success else "220,80,80"  # rgb, verde/vermelho
        icon_name = "mdi6.check-circle" if success else "mdi6.alert-circle"
        icon_color = "#7CE0B0" if success else "#ff8888"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("ResHeader")
        header.setFixedHeight(46)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 14, 0)

        icon = QLabel()
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(16, 16))
        icon.setStyleSheet(f"QLabel {{ background: rgba({accent},40); border-radius: 7px; }}")

        lbl = QLabel(title)
        lbl.setFont(QFont(FONT_FAMILY, 10, QFont.Bold))
        lbl.setStyleSheet("color: #ecf4ff;")

        btn_x = _CloseLabel(self)
        btn_x.mousePressEvent = lambda e: self.accept()

        h_layout.addWidget(icon)
        h_layout.addSpacing(8)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        h_layout.addWidget(btn_x)

        body = QFrame()
        body.setObjectName("ResBody")
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(20, 16, 20, 18)
        b_layout.setSpacing(14)

        msg = QLabel(message or "(sem saída)")
        msg.setFont(QFont(FONT_FAMILY, 9))
        msg.setStyleSheet("color: #c8d4e0;")
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_layout.addWidget(msg)

        if detail:
            detail_lbl = QLabel(detail)
            detail_lbl.setFont(QFont(FONT_FAMILY, 8))
            detail_lbl.setStyleSheet("color: #8a97a6;")
            detail_lbl.setWordWrap(True)
            detail_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            b_layout.addWidget(detail_lbl)

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("ResBtnOk")
        btn_ok.setFixedWidth(90)
        btn_ok.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        b_layout.addLayout(btn_row)

        root.addWidget(header)
        root.addWidget(body)

        self.setStyleSheet(f"""
            QFrame#ResHeader {{
                background: rgba({accent}, 35);
                border-bottom: 1px solid rgba({accent}, 100);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
            QFrame#ResBody {{
                background: #080c14;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }}
            QPushButton#ResBtnOk {{
                background: rgba(10, 15, 25, 230);
                border: 1px solid rgba({accent}, 120);
                border-radius: 8px; color: #ecf4ff;
                font-family: "{FONT_FAMILY}";
                font-size: 11px; padding: 5px 0;
            }}
            QPushButton#ResBtnOk:hover {{
                background: rgba({accent}, 40);
                border-color: rgba({accent}, 200);
            }}
        """)
        self.adjustSize()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(event.globalPosition().toPoint() - self._drag)


class CheckupWorker(QThread):
    finished_checkup = Signal(object, dict, int)  # report, tamanhos por categoria, total

    def run(self) -> None:
        report = run_full_checkup()
        try:
            from core.system.cleanup import estimate_cleanup_size
            per_category, total = estimate_cleanup_size()
        except Exception:
            per_category, total = {}, 0
        self.finished_checkup.emit(report, per_category, total)


class HelperActionWorker(QThread):
    """Dispara uma ação privilegiada via carbonara-helper (pkexec) fora
    da thread da UI, emitindo cada linha de stdout assim que sai — em vez
    de esperar o processo inteiro terminar pra só então mostrar tudo de
    uma vez. Reaproveitável por qualquer botão de ação da página."""
    progress_line = Signal(str)
    finished_action = Signal(int, str, str)  # returncode, stdout completo, stderr completo

    def __init__(self, action: str, args: dict, parent=None):
        super().__init__(parent)
        self._action = action
        self._args = args

    def run(self) -> None:
        import os
        import subprocess
        import json as _json

        display = os.environ.get("DISPLAY", "")
        xauthority = os.environ.get("XAUTHORITY", "")
        payload = _json.dumps(self._args)
        cmd = ["pkexec", "/usr/local/bin/carbonara-helper", display, xauthority, self._action, payload]

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
        except Exception as exc:
            self.finished_action.emit(1, "", str(exc))
            return

        collected: list[str] = []
        if proc.stdout is not None:
            for line in proc.stdout:
                line = line.rstrip("\n")
                if line:
                    collected.append(line)
                    self.progress_line.emit(line)

        stderr = ""
        if proc.stderr is not None:
            stderr = proc.stderr.read()
        proc.wait()
        self.finished_action.emit(proc.returncode, "\n".join(collected), stderr)


class DoctorArchPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet(f"""
            QWidget {{ background: transparent; }}
            QPushButton {{
                padding: 9px 16px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 14);
                background: rgba(255, 255, 255, 6);
                color: {TEXT};
                font-family: "{FONT_FAMILY}";
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 24);
            }}
            QPushButton#BackButton {{
                background: transparent;
                border: none;
                color: {MUTED};
                font-weight: normal;
                padding: 4px 0px;
            }}
            QPushButton#BackButton:hover {{
                color: {TEXT};
                background: transparent;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # ── Cabeçalho padrão do app (logo/specs/menu + Início) ─────────────
        from ui.main_window import AppHeaderBlock  # import adiado — evita import circular

        self.app_header = AppHeaderBlock(back_button=True)
        self.app_header.back_clicked.connect(self.back_requested.emit)
        root.addWidget(self.app_header)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 14, 0, 0)
        title_block.setSpacing(2)
        page_title = QLabel("Doctor Arch")
        page_title.setFont(QFont(FONT_FAMILY, 22, QFont.Bold))
        page_title.setStyleSheet(f"color: {TEXT};")
        title_block.addWidget(page_title)
        root.addLayout(title_block)

        # ── Conteúdo em coluna única ──────────────────────────────────────
        content_col = QVBoxLayout()
        content_col.setSpacing(12)
        root.addLayout(content_col, 1)

        # Hero: health score — cor/borda variam pela faixa do score,
        # botão de checkup mora aqui dentro (não solto no topo da página,
        # sem relação visual com nada).
        self.hero = QFrame()
        self.hero.setStyleSheet(CARD_STYLE)
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(22)

        self.ring = HealthRing(100)
        hero_layout.addWidget(self.ring)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(4)
        self.hero_title = QLabel("Rodando checkup...")
        self.hero_title.setFont(QFont(FONT_FAMILY, 15, QFont.Bold))
        self.hero_title.setStyleSheet(f"color: {TEXT};")
        self.hero_status = QLabel("")
        self.hero_status.setFont(QFont(FONT_FAMILY, 11))
        hero_text.addWidget(self.hero_title)
        hero_text.addWidget(self.hero_status)
        hero_layout.addLayout(hero_text, 1)

        checkup_block = QVBoxLayout()
        checkup_block.setSpacing(6)
        checkup_block.setAlignment(Qt.AlignRight)
        self.btn_checkup = QPushButton("↻  Rodar checkup")
        self.btn_checkup.clicked.connect(self.run_checkup)
        self.hero_last_check = QLabel("")
        self.hero_last_check.setFont(QFont(FONT_FAMILY, 9))
        self.hero_last_check.setStyleSheet(f"color: {FAINT};")
        self.hero_last_check.setAlignment(Qt.AlignRight)
        checkup_block.addWidget(self.btn_checkup)
        checkup_block.addWidget(self.hero_last_check)
        hero_layout.addLayout(checkup_block)

        content_col.addWidget(self.hero)

        lbl_findings = QLabel("O QUE PRECISA DE ATENÇÃO")
        lbl_findings.setFont(QFont(FONT_FAMILY, 10, QFont.Bold))
        lbl_findings.setStyleSheet(f"color: {FAINT}; letter-spacing: 0.5px;")
        content_col.addWidget(lbl_findings)

        self.findings_container = QVBoxLayout()
        self.findings_container.setSpacing(0)
        findings_frame = QFrame()
        findings_frame.setStyleSheet("QFrame { border: 1px solid rgba(255,255,255,12); border-radius: 14px; }")
        findings_frame.setLayout(self.findings_container)
        content_col.addWidget(findings_frame)

        lbl_actions = QLabel("MANUTENÇÃO")
        lbl_actions.setFont(QFont(FONT_FAMILY, 10, QFont.Bold))
        lbl_actions.setStyleSheet(f"color: {FAINT}; letter-spacing: 0.5px;")
        content_col.addWidget(lbl_actions)

        self.actions_row = QGridLayout()
        self.actions_row.setSpacing(12)
        content_col.addLayout(self.actions_row)

        # Log ao vivo — some por padrão, aparece durante uma ação
        self.progress_frame = QFrame()
        self.progress_frame.setStyleSheet(
            "QFrame { border: 1px solid rgba(52,211,153,40); border-radius: 12px; background: #0d0e13; }"
        )
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(14, 10, 14, 10)
        progress_layout.setSpacing(4)
        self.progress_lines_layout = QVBoxLayout()
        self.progress_lines_layout.setSpacing(3)
        progress_layout.addLayout(self.progress_lines_layout)
        self.progress_frame.hide()
        content_col.addWidget(self.progress_frame)

        lbl_vitals = QLabel("VITALS DO SISTEMA")
        lbl_vitals.setFont(QFont(FONT_FAMILY, 10, QFont.Bold))
        lbl_vitals.setStyleSheet(f"color: {FAINT}; letter-spacing: 0.5px;")
        content_col.addWidget(lbl_vitals)

        self.vitals_row = QGridLayout()
        self.vitals_row.setSpacing(12)
        content_col.addLayout(self.vitals_row)

        content_col.addStretch()

        self._worker: CheckupWorker | None = None
        self._action_worker: HelperActionWorker | None = None
        self.run_checkup()

    def run_checkup(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.btn_checkup.setEnabled(False)
        self.hero_title.setText("Rodando checkup...")
        worker = CheckupWorker(parent=self)
        worker.finished_checkup.connect(self._on_checkup_done)
        self._worker = worker
        worker.start()

    def _dispatch_action(self, action: str, args: dict, btn: QPushButton) -> None:
        if not OperationManager.assert_available():
            return
        OperationManager.start(f"doctor_{action}", "Doctor Arch — ação privilegiada")
        btn.setEnabled(False)
        btn.setText("Executando...")
        self.btn_checkup.setEnabled(False)

        self._clear_layout(self.progress_lines_layout)
        self.progress_frame.show()

        worker = HelperActionWorker(action, args, parent=self)
        worker.progress_line.connect(self._on_progress_line)
        worker.finished_action.connect(self._on_action_done)
        self._action_worker = worker
        worker.start()

    def _on_progress_line(self, line: str) -> None:
        lbl = QLabel(f"›  {line}")
        lbl.setFont(QFont(FONT_FAMILY, 10))
        lbl.setStyleSheet(f"color: {TEXT};")
        lbl.setWordWrap(True)
        self.progress_lines_layout.addWidget(lbl)

    def _on_action_done(self, returncode: int, stdout: str, stderr: str) -> None:
        OperationManager.finish()
        self.progress_frame.hide()
        dialog = ActionResultDialog(
            success=(returncode == 0),
            message=stdout or "(sem saída)",
            detail=stderr if returncode != 0 else "",
            parent=self.window(),
        )
        dialog.exec()
        # Reroda o checkup inteiro — mais simples e confiável do que
        # tentar remover só a linha do achado corrigido, e garante que
        # o resto da página (score, vitals, tamanho de limpeza) reflita
        # o estado real.
        self.run_checkup()

    def _run_finding_action(self, finding_id: str, btn: QPushButton) -> None:
        mapping = FINDING_ACTION_MAP.get(finding_id)
        if mapping is None:
            return
        action, args = mapping
        self._dispatch_action(action, args, btn)

    def _show_finding_detail(self, finding: Finding) -> None:
        dialog = FindingDetailDialog(finding, guidance=FINDING_GUIDANCE.get(finding.id, ""), parent=self.window())
        dialog.exec()

    def _run_cleanup_all(self, btn: QPushButton) -> None:
        from core.system.cleanup import CATEGORIES
        self._dispatch_action("doctor.cleanup", {"categories": CATEGORIES}, btn)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _on_checkup_done(self, report: DoctorReport, cleanup_sizes: dict, cleanup_total: int) -> None:
        self.btn_checkup.setEnabled(True)
        self.ring.set_score(report.score)

        if report.score >= 80:
            band_color, band_rgb = ACCENT_GREEN, "52,211,153"
        elif report.score >= 50:
            band_color, band_rgb = ACCENT_AMBER, "251,191,36"
        else:
            band_color, band_rgb = ACCENT_RED, "248,113,113"

        self.hero.setStyleSheet(f"""
            QFrame {{
                background: rgba({band_rgb}, 8);
                border: 1px solid rgba({band_rgb}, 70);
                border-radius: 14px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)

        if report.critical_count == 0 and report.warning_count == 0:
            self.hero_title.setText("Seu sistema está impecável")
            self.hero_status.setText("Nada pra revisar agora")
        elif report.critical_count == 0:
            self.hero_title.setText("Seu sistema está quase perfeito")
            self.hero_status.setText(f"{report.warning_count} aviso(s) pendente(s) · nada crítico agora")
        else:
            self.hero_title.setText("Seu sistema precisa de atenção")
            parts = [f"{report.critical_count} crítico(s)"]
            if report.warning_count:
                parts.append(f"{report.warning_count} aviso(s)")
            self.hero_status.setText(" · ".join(parts))
        self.hero_status.setStyleSheet(f"color: {band_color};")
        self.hero_last_check.setText("verificado agora mesmo")

        # Findings
        self._clear_layout(self.findings_container)
        actionable = [f for f in report.findings if f.level != "ok"]
        if not actionable:
            ok_row = QLabel("Nenhum achado — tudo em ordem.")
            ok_row.setFont(QFont(FONT_FAMILY, 11))
            ok_row.setStyleSheet(f"color: {MUTED}; padding: 16px; background: #0d0e13; border-radius: 14px;")
            self.findings_container.addWidget(ok_row)
        else:
            for i, finding in enumerate(actionable):
                self.findings_container.addWidget(
                    FindingRow(
                        finding, is_last=(i == len(actionable) - 1),
                        on_action=self._run_finding_action, on_view=self._show_finding_detail,
                    )
                )

        # Ações rápidas (4 cards)
        self._clear_layout(self.actions_row)
        timers_finding = next((f for f in report.findings if f.id == "critical_timers"), None)
        volumes_finding = next((f for f in report.findings if f.id == "volumes"), None)
        aur_finding = next((f for f in report.findings if f.id.startswith("aur_")), None)

        from core.system.cleanup import format_size
        cleanup_subtitle = f"{format_size(cleanup_total)} em 5 categorias" if cleanup_total else "Nada a limpar"
        cleanup_card = ActionCard("mdi6.broom", "Limpeza", cleanup_subtitle,
                                  action_label="Limpar", on_action=self._run_cleanup_all)
        volumes_card = ActionCard(
            "mdi6.harddisk", "Volumes",
            volumes_finding.detail if volumes_finding else "não verificado",
            status="ok" if volumes_finding and volumes_finding.level == "ok" else "atenção",
            status_color=ACCENT_GREEN if volumes_finding and volumes_finding.level == "ok" else ACCENT_RED,
        )
        automacao_card = ActionCard(
            "mdi6.timer-check-outline", "Automação",
            timers_finding.detail if timers_finding else "não verificado",
            status="ok" if timers_finding and timers_finding.level == "ok" else "atenção",
            status_color=ACCENT_GREEN if timers_finding and timers_finding.level == "ok" else ACCENT_RED,
        )
        watchlist_card = ActionCard(
            "mdi6.eye-outline", "Watchlist AUR",
            aur_finding.detail if aur_finding else "nenhum pacote observado",
            status="1 pkg" if aur_finding else None,
            status_color=ACCENT_BLUE_LIGHT,
        )
        self.actions_row.addWidget(cleanup_card, 0, 0)
        self.actions_row.addWidget(volumes_card, 0, 1)
        self.actions_row.addWidget(automacao_card, 0, 2)
        self.actions_row.addWidget(watchlist_card, 0, 3)

        # Vitals (fileira horizontal, label/valor)
        self._clear_layout(self.vitals_row)
        v = report.vitals

        raid_ok = v.raid_state == "clean"
        raid_card = VitalCard(
            v.raid_level.upper() if v.raid_level != "-" else "RAID",
            v.raid_state if v.raid_device != "-" else "n/a",
            value_color=ACCENT_GREEN if raid_ok else ACCENT_RED,
        )
        smart_ok = v.smart_total > 0 and v.smart_ok == v.smart_total
        smart_card = VitalCard(
            "SMART",
            f"{v.smart_ok}/{v.smart_total} ok" if v.smart_total else "n/a",
            value_color=ACCENT_GREEN if smart_ok else ACCENT_RED,
        )
        boot_card = VitalCard("BOOT TIME", v.boot_time, value_color=TEXT)
        kernel_card = VitalCard("KERNEL", v.kernel, value_color=TEXT)

        for i, card in enumerate((raid_card, smart_card, boot_card, kernel_card)):
            self.vitals_row.addWidget(card, 0, i)
