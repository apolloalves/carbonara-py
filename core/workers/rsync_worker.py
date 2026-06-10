from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal


class RsyncWorker(QThread):
    progress_changed = Signal(int)
    status_changed = Signal(str)
    file_changed = Signal(str)
    log_line = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(
        self,
        command: list[str],
        title: str = "",
        log_path: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.command = command
        self.title = title
        self.log_path = Path(log_path) if log_path else None
        self._process: subprocess.Popen | None = None

    def kill(self) -> None:
        """Mata o processo rsync pelo PID — não bloqueia a thread chamadora."""
        proc = self._process
        if proc is not None:
            try:
                proc.kill()   # SIGKILL imediato, sem wait()
            except OSError:
                pass

    def run(self) -> None:
        log_fh = None
        try:
            if self.log_path:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                log_fh = self.log_path.open("a", encoding="utf-8")

            self.status_changed.emit(self.title or "Executando...")

            self._process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
            assert self._process.stdout is not None

            last_percent = -1
            percent_regex = re.compile(r"(\d{1,3})%")

            for raw_line in self._process.stdout:
                line = raw_line.rstrip("\n")
                if not line.strip():
                    continue

                if log_fh:
                    log_fh.write(line + "\n")
                    log_fh.flush()

                if line.startswith("Copiando: "):
                    current_file = line.replace("Copiando: ", "", 1).strip()
                    self.file_changed.emit(current_file)
                    self.log_line.emit(f"Copiando: {current_file}")
                    continue

                if line.startswith("deleting "):
                    continue

                match = percent_regex.search(line)
                if match:
                    try:
                        percent = int(match.group(1))
                        if 0 <= percent <= 100 and percent != last_percent:
                            last_percent = percent
                            self.progress_changed.emit(percent)
                            self.status_changed.emit(
                                f"{self.title or 'Executando...'} {percent}%"
                            )
                    except ValueError:
                        pass
                    continue

                self.log_line.emit(line)

            rc = self._process.wait()
            if rc == 0:
                self.progress_changed.emit(100)
                self.status_changed.emit("Concluído com sucesso.")
                self.finished_ok.emit()
            else:
                self.failed.emit(f"rsync terminou com código {rc}")

        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self._process = None
            if log_fh:
                log_fh.close()
