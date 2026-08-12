from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

# `gio copy --progress` na prática imprime linhas tipo:
#   "Transferred 131.7 MB out of 67.7 GB (4.1 MB/s)"
# — sem porcentagem explícita, então calculamos a partir dos valores
# "transferido" e "total" (convertendo pra bytes). Também vem com
# sequências de escape ANSI (cursor/limpeza de linha) porque o gio
# assume um terminal interativo — precisam ser removidas antes do
# regex, senão a linha não bate.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\r")
_GIO_PROGRESS_RE = re.compile(
    r"Transferred\s+([\d.]+)\s*(B|KB|MB|GB|TB)\s+out of\s+([\d.]+)\s*(B|KB|MB|GB|TB)"
    r"(?:\s+\(([\d.]+)\s*(B|KB|MB|GB|TB)/s\))?",
    re.IGNORECASE,
)

_UNIT_MULTIPLIER = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
    "TB": 1024 ** 4,
}


def _to_bytes(value: str, unit: str) -> float:
    return float(value) * _UNIT_MULTIPLIER[unit.upper()]


class GDriveUploadWorker(QThread):
    """Envia um arquivo pro Google Drive via GVfs (a mesma conexão que o
    GNOME Online Accounts já mantém — sem precisar de OAuth/API própria).
    Roda na sessão normal do usuário, sem pkexec, já que é a própria conta
    Google do usuário sendo usada, sem necessidade de privilégio elevado.

    Interface de sinais compatível com ClonezillaCompressWorker/RsyncWorker
    (progress_changed, status_changed, log_line, finished_ok, failed, kill),
    pra plugar direto no ClonezillaProgressDialog já existente.
    """

    progress_changed = Signal(int)
    status_changed = Signal(str)
    detail_changed = Signal(str)
    log_line = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, local_path: Path, target_uri: str, parent=None):
        super().__init__(parent)
        self.local_path = Path(local_path)
        self.target_uri = target_uri.rstrip("/")
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    def kill(self) -> None:
        self._cancelled = True
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    cancel = kill

    def run(self) -> None:
        try:
            if not self.local_path.exists():
                self.failed.emit(f"Arquivo não encontrado: {self.local_path}")
                return

            dest_uri = f"{self.target_uri}/{self.local_path.name}"

            self.status_changed.emit(f"Enviando {self.local_path.name} para o Google Drive...")
            self.log_line.emit(f"$ gio copy --progress {self.local_path} {dest_uri}")

            self._proc = subprocess.Popen(
                ["gio", "copy", "--progress", str(self.local_path), dest_uri],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            last_emit = -1
            assert self._proc.stdout is not None
            for raw_line in self._proc.stdout:
                line = _ANSI_ESCAPE_RE.sub("", raw_line).strip()
                if not line:
                    continue
                m = _GIO_PROGRESS_RE.search(line)
                if m:
                    done_val, done_unit, total_val, total_unit, rate_val, rate_unit = m.groups()
                    done_bytes = _to_bytes(done_val, done_unit)
                    gio_total_bytes = _to_bytes(total_val, total_unit)
                    pct = min(100, int(done_bytes / gio_total_bytes * 100)) if gio_total_bytes else 0
                    if pct != last_emit:
                        self.progress_changed.emit(pct)
                        last_emit = pct
                        rate_txt = f"   ·   {rate_val} {rate_unit}/s" if rate_val else ""
                        self.detail_changed.emit(
                            f"{done_val} {done_unit} de {total_val} {total_unit}{rate_txt}"
                        )
                else:
                    self.log_line.emit(line)

            rc = self._proc.wait()

            if self._cancelled:
                self.failed.emit("Envio cancelado pelo usuário.")
                return

            if rc != 0:
                self.failed.emit(
                    f"gio copy terminou com código {rc}. Confira se a conta Google "
                    f"ainda está conectada em Configurações → Online Accounts."
                )
                return

            self.log_line.emit(f"✓ Enviado para: {dest_uri}")
            self.finished_ok.emit()

        except FileNotFoundError:
            self.failed.emit(
                "Comando 'gio' não encontrado — verifique se o gvfs/glib2 está instalado."
            )
        except Exception as exc:
            self.failed.emit(str(exc))
