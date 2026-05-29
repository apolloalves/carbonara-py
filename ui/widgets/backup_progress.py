from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar,
    QPlainTextEdit, QPushButton, QHBoxLayout
)

class BackupProgressDialog(QDialog):
    def __init__(self, title="Carbonara Backup", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 520)
        self.setModal(True)

        self._workers = []

        layout = QVBoxLayout(self)

        self.lbl_title = QLabel("Preparando snapshot...")
        self.lbl_title.setAlignment(Qt.AlignCenter)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")

        self.lbl_status = QLabel("Aguardando início...")
        self.lbl_status.setAlignment(Qt.AlignCenter)

        self.lbl_current = QLabel("Arquivo atual: —")
        self.lbl_current.setAlignment(Qt.AlignCenter)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        btn_row = QHBoxLayout()
        self.btn_close = QPushButton("Fechar")
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)

        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_close)

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.progress)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.lbl_current)
        layout.addWidget(self.log_view)
        layout.addLayout(btn_row)

    def register_worker(self, worker):
        self._workers.append(worker)
        worker.finished_ok.connect(lambda: self._cleanup_worker(worker))
        worker.failed.connect(lambda _: self._cleanup_worker(worker))

    def _cleanup_worker(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)

    def append_log(self, text: str):
        self.log_view.appendPlainText(text)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def set_current_file(self, text: str):
        self.lbl_current.setText(f"Arquivo atual: {text}")

    def set_running(self, running: bool):
        self.btn_close.setEnabled(not running)

    def closeEvent(self, event):
        if any(worker.isRunning() for worker in self._workers):
            event.ignore()
            self.set_status("Backup em execução...")
            return
        super().closeEvent(event)
