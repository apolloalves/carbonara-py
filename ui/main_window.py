import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt, QRect, QEvent
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QBrush,
    QKeyEvent,
    QFontMetrics,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


BG = "#000000"
BORDER = "#1f5cff"
LIGHT_BLUE = "#23a6ff"
ARCH_BLUE = "#1793d1"
TEXT = "#ecf4ff"
MUTED = "#9aa6b2"
ACTIVE_BG = "rgba(12, 24, 48, 185)"


@dataclass(frozen=True)
class MenuEntry:
    number: int
    title: str
    desc: str
    icon: str


MENU_ENTRIES = [
    MenuEntry(1, "Dashboard", "Monitor system information and quick status", "▣"),
    MenuEntry(2, "Network", "Diagnose and configure network settings", "◌"),
    MenuEntry(3, "Packages", "Manage packages, mirrors and updates", "⬚"),
    MenuEntry(4, "Wizards", "Guided actions for backups and maintenance", "⌁"),
    MenuEntry(5, "Maintenance", "Clean caches, logs and system junk", "◈"),
    MenuEntry(6, "Performance", "Optimize boot, swap and system responsiveness", "⚙"),
    MenuEntry(7, "Services", "Inspect, enable and disable system services", "↻"),
    MenuEntry(8, "Exit", "Exit Carbonara", "▭"),
]

ARCH_ART = [
    "                  -`",
    "                 .o+`",
    "                `ooo/",
    "               `+oooo:",
    "              `+oooooo:",
    "              -+oooooo+:",
    "            `/:-:++oooo+:",
    "           `/++++/+++++++:",
    "          `/++++++++++++++:",
    "         `/+++ooooooooooooo/`",
    "        ./ooosssso++osssssso+`",
    "       .oossssso-````/ossssss+`",
    "      -osssssso.      :ssssssso.",
    "     :osssssss/        osssso+++.",
    "    /ossssssss/        +ssssooo/-",
    "  `/ossssso+/:-        -:/+osssso+-",
    " `+sso+:-`                 `.-/+oso:",
    "`++:.                           `-/+/",
]


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class MenuLine(QFrame):
    def __init__(self, entry: MenuEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.active = False
        self.setFixedHeight(42)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_active(self, value: bool):
        self.active = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.active:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(12, 24, 48, 185)))
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 8, 8)
            painter.setBrush(QColor(LIGHT_BLUE))
            painter.drawRect(2, 2, 8, self.height() - 4)

        icon_color = QColor(LIGHT_BLUE) if self.active else QColor(ARCH_BLUE)
        num_color = QColor(TEXT) if self.active else QColor(LIGHT_BLUE)

        painter.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        painter.setPen(icon_color)
        painter.drawText(QRect(10, 0, 28, self.height()), Qt.AlignCenter, self.entry.icon)

        painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        painter.setPen(num_color)
        painter.drawText(QRect(50, 0, 26, self.height()), Qt.AlignVCenter | Qt.AlignLeft, str(self.entry.number))

        painter.setPen(QColor(TEXT))
        painter.drawText(QRect(90, 0, 220, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.entry.title)

        painter.setPen(QColor(MUTED))
        painter.setFont(QFont("DejaVu Sans Mono", 10))
        painter.drawText(QRect(320, 0, 650, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.entry.desc)


class TopBanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        painter.fillRect(self.rect(), QColor(BG))
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 14, 14)

        left_w = clamp(int(w * 0.28), 280, 380)
        divider_x = left_w + clamp(int(w * 0.015), 18, 28)
        painter.drawLine(divider_x, 20, divider_x, h - 20)

        arch_font_size = clamp(int(h * 0.029), 8, 10)
        painter.setFont(QFont("DejaVu Sans Mono", arch_font_size))
        painter.setPen(QColor(ARCH_BLUE))
        y = 28
        line_step = clamp(int(h * 0.044), 13, 16)
        for i, line in enumerate(ARCH_ART):
            painter.drawText(28, y + i * line_step, line)

        title_x = divider_x + clamp(int(w * 0.03), 28, 44)
        title_font_size = clamp(int(w * 0.042), 52, 72)
        painter.setFont(QFont("DejaVu Sans Mono", title_font_size, QFont.Bold))

        painter.setPen(QColor(25, 25, 25))
        painter.drawText(title_x + 2, 96, "CARBONARA")
        painter.setPen(QColor(240, 240, 240))
        painter.drawText(title_x, 94, "CARBONARA")

        line_y = clamp(int(h * 0.53), 155, 176)
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawLine(title_x, line_y, w - 32, line_y)

        center_x = int((title_x + (w - 32)) / 2)
        painter.setBrush(QColor(LIGHT_BLUE))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center_x - 6, line_y - 6, 12, 12)

        subtitle_w = w - title_x - 32
        subtitle_font = clamp(int(w * 0.015), 16, 20)
        painter.setPen(QColor(TEXT))
        painter.setFont(QFont("DejaVu Sans Mono", subtitle_font, QFont.Bold))
        painter.drawText(
            QRect(title_x, 186, subtitle_w, 34),
            Qt.AlignHCenter,
            "Carbonara CLI",
        )

        painter.setPen(QColor(MUTED))
        painter.setFont(QFont("DejaVu Sans Mono", clamp(int(w * 0.010), 11, 13)))
        painter.drawText(
            QRect(title_x, 220, subtitle_w, 30),
            Qt.AlignHCenter,
            "Apollo Alves • Arch Linux",
        )


class SectionHeader(QFrame):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text
        self.setFixedHeight(28)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        font = QFont("DejaVu Sans Mono", 18, QFont.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(self.text)

        gap = 14
        text_x = max(0, (w - text_w) // 2)

        left_end = max(0, text_x - gap)
        right_start = min(w, text_x + text_w + gap)

        painter.setPen(QPen(QColor("#b8b8b8"), 1))
        painter.drawLine(0, h // 2, left_end, h // 2)
        painter.drawLine(right_start, h // 2, w, h // 2)

        painter.setPen(QColor(LIGHT_BLUE))
        painter.drawText(QRect(text_x, 0, text_w, h), Qt.AlignCenter, self.text)


class MenuWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Carbonara CLI")
        self.resize(1280, 900)
        self.setMinimumSize(1100, 780)
        self.setStyleSheet(f"background: {BG};")

        self.current_index = 0
        self.lines: list[MenuLine] = []
        self._build_ui()
        self._refresh_selection()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        self.outer_layout = QVBoxLayout(central)
        self.outer_layout.setContentsMargins(18, 18, 18, 18)
        self.outer_layout.setSpacing(16)
        self.outer_layout.setAlignment(Qt.AlignTop)

        self.shell = QFrame()
        self.shell.setMinimumWidth(980)
        self.shell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.shell.setStyleSheet(
            f"""
            QFrame {{
                background: rgba(0, 0, 0, 235);
                border: 1px solid {BORDER};
                border-radius: 16px;
            }}
            """
        )

        self.shell_layout = QVBoxLayout(self.shell)
        self.shell_layout.setContentsMargins(16, 14, 16, 14)
        self.shell_layout.setSpacing(12)

        self.banner = TopBanner()
        self.shell_layout.addWidget(self.banner)

        self.header = SectionHeader("MAIN MENU")
        self.shell_layout.addWidget(self.header)

        self.body = QWidget()
        self.body.setStyleSheet("background: transparent; border: none;")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setSpacing(2)

        for i, entry in enumerate(MENU_ENTRIES):
            line = MenuLine(entry)
            self.lines.append(line)
            if i == self.current_index:
                line.set_active(True)
            self.body_layout.addWidget(line)

        self.shell_layout.addWidget(self.body)

        self.footer = QFrame()
        self.footer.setStyleSheet(
            f"""
            QFrame {{
                border: 1px solid {BORDER};
                border-radius: 10px;
                background: rgba(6, 12, 20, 255);
            }}
            """
        )
        self.footer.setFixedHeight(64)
        self.footer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(12, 6, 12, 6)
        footer_layout.setSpacing(6)

        self.prompt = QLabel("Select an option [1-8]:")
        self.prompt.setFont(QFont("DejaVu Sans Mono", 14, QFont.Bold))
        self.prompt.setStyleSheet(
            f"""
            color: {LIGHT_BLUE};
            background: transparent;
            border: none;
            """
        )
        self.prompt.setMinimumWidth(220)
        self.prompt.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        self.input_box = QLineEdit()
        self.input_box.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
        self.input_box.setStyleSheet(
            f"""
            QLineEdit {{
                color: {TEXT};
                background: transparent;
                border: none;
                padding: 0px;
            }}
            """
        )
        self.input_box.installEventFilter(self)

        footer_layout.addWidget(self.prompt)
        footer_layout.addWidget(self.input_box, 1)
        self.shell_layout.addWidget(self.footer)

        self.status = QLabel("Use ↑ ↓ to move, Enter to select")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont("DejaVu Sans Mono", 9))
        self.status.setStyleSheet(
            f"""
            color: {LIGHT_BLUE};
            background: transparent;
            border: none;
            """
        )
        self.shell_layout.addWidget(self.status)

        self.outer_layout.addWidget(self.shell)
        self.input_box.setFocus()
        self._apply_responsive_metrics()

    def _apply_responsive_metrics(self):
        available_w = max(980, self.width() - 36)
        side_margin = clamp(int(available_w * 0.08), 60, 200)
        self.body_layout.setContentsMargins(side_margin, 0, side_margin, 0)
        self.prompt.setMinimumWidth(clamp(int(available_w * 0.18), 220, 320))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_metrics()

    def _refresh_selection(self):
        for i, line in enumerate(self.lines):
            line.set_active(i == self.current_index)

    def _move(self, step: int):
        self.current_index = (self.current_index + step) % len(self.lines)
        self._refresh_selection()
        entry = MENU_ENTRIES[self.current_index]
        self.status.setText(f"Selected: {entry.number} — {entry.title}")

    def _confirm_current(self):
        entry = MENU_ENTRIES[self.current_index]
        self.status.setText(f"Confirmed: {entry.number} — {entry.title}")
        if entry.title == "Exit":
            self.close()

    def _accept_typed_choice(self):
        text = self.input_box.text().strip()
        if not text.isdigit():
            self.status.setText("Type only a number from the menu.")
            self.input_box.selectAll()
            return

        choice = int(text)
        for idx, entry in enumerate(MENU_ENTRIES):
            if entry.number == choice:
                self.current_index = idx
                self._refresh_selection()
                self.input_box.clear()
                self._confirm_current()
                return

        self.status.setText(f"Invalid choice: {choice}")
        self.input_box.selectAll()

    def eventFilter(self, obj, event):
        if obj is self.input_box and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Up, Qt.Key_W):
                self._move(-1)
                return True
            if key in (Qt.Key_Down, Qt.Key_S):
                self._move(1)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._accept_typed_choice()
                return True
            if key == Qt.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_W):
            self._move(-1)
            return
        if key in (Qt.Key_Down, Qt.Key_S):
            self._move(1)
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._confirm_current()
            return
        if key == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("DejaVu Sans Mono", 10))

    win = MenuWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
