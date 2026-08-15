from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

# `rclone copy --stats 1s --stats-one-line` imprime uma linha por
# atualização, tipo:
#   "2026/08/13 12:05:35 INFO  :    11.617 GiB / 63.064 GiB, 18%, 2.713 MiB/s, ETA 5h23m36s"
# — sem o prefixo "Transferred:" (diferente do que a documentação
# sugere) — casa só o padrão "X / Y, Z%, RATE/s" em qualquer lugar da
# linha.
_RCLONE_STATS_RE = re.compile(
    r"([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+),\s*(\d{1,3})%,\s*([\d.]+\s*\w+/s)"
)

_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 8

_UNIT_MULTIPLIER = {
    "B": 1,
    "KIB": 1024, "KB": 1024,
    "MIB": 1024 ** 2, "MB": 1024 ** 2,
    "GIB": 1024 ** 3, "GB": 1024 ** 3,
    "TIB": 1024 ** 4, "TB": 1024 ** 4,
}


def _parse_size(text: str) -> float:
    """Converte um valor tipo '11.617 GiB' em bytes."""
    m = re.match(r"([\d.]+)\s*(\w+)", text.strip())
    if not m:
        return 0.0
    value, unit = m.groups()
    return float(value) * _UNIT_MULTIPLIER.get(unit.upper(), 1)


class RcloneUploadWorker(QThread):
    """Envia um arquivo pro Google Drive via rclone (mais eficiente que o
    gio/GVfs — transferência em pedaços, retry embutido). Precisa de um
    remote 'gdrive' já configurado (`rclone config`) com `root_folder_id`
    apontando pra pasta CLONEZILLA real no Drive.

    Roda na sessão normal do usuário, sem pkexec — usa a credencial
    própria do rclone (arquivo `~/.config/rclone/rclone.conf`), não a
    conexão do GNOME Online Accounts.

    Interface de sinais compatível com ClonezillaCompressWorker/RsyncWorker
    (progress_changed, status_changed, detail_changed, log_line,
    finished_ok, failed, kill/cancel).
    """

    progress_changed = Signal(int)
    status_changed = Signal(str)
    detail_changed = Signal(str)
    bytes_changed = Signal(float, float)
    log_line = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(
        self, local_path: Path, remote_folder: str,
        remote_name: str = "gdrive", parent=None,
    ):
        super().__init__(parent)
        self.local_path = Path(local_path)
        # Caminho relativo dentro do remote (ex: "2026/JUNE") — o
        # root_folder_id do remote já aponta pra pasta CLONEZILLA, então
        # isso vira CLONEZILLA/2026/JUNE no Drive de verdade.
        self.remote_folder = remote_folder.strip("/")
        self.remote_name = remote_name
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

            dest = f"{self.remote_name}:{self.remote_folder}/"
            self.status_changed.emit(f"Enviando {self.local_path.name} via rclone...")

            for attempt in range(1, _MAX_RETRIES + 1):
                if self._cancelled:
                    self.failed.emit("Envio cancelado pelo usuário.")
                    return

                rc = self._attempt_upload(dest, attempt)

                if self._cancelled:
                    self.failed.emit("Envio cancelado pelo usuário.")
                    return

                if rc == 0:
                    self.log_line.emit(f"✓ Enviado para: {dest}{self.local_path.name}")
                    self.finished_ok.emit()
                    return

                if attempt < _MAX_RETRIES:
                    self.log_line.emit(
                        f"AVISO: tentativa {attempt}/{_MAX_RETRIES} falhou (código {rc}) — "
                        f"tentando de novo em {_RETRY_DELAY_SECONDS}s..."
                    )
                    self.status_changed.emit(
                        f"Falha temporária — tentando de novo ({attempt}/{_MAX_RETRIES})..."
                    )
                    self.sleep(_RETRY_DELAY_SECONDS)

            self.failed.emit(
                f"rclone copy falhou após {_MAX_RETRIES} tentativas (último código: {rc}). "
                f"Confira sua conexão e o remote 'gdrive' (rclone config)."
            )

        except FileNotFoundError:
            self.failed.emit(
                "Comando 'rclone' não encontrado — instale com: sudo pacman -S rclone"
            )
        except Exception as exc:
            self.failed.emit(str(exc))

    def _attempt_upload(self, dest: str, attempt: int) -> int:
        cmd_list = [
            "rclone", "copy",
            "--stats", "1s", "--stats-one-line", "-v",
            "--retries", "5",
            str(self.local_path), dest,
        ]
        cmd_label = "$ " + " ".join(cmd_list)
        if attempt > 1:
            cmd_label += f"   (tentativa {attempt}/{_MAX_RETRIES})"
        self.log_line.emit(cmd_label)

        self._proc = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        last_emit = -1
        assert self._proc.stdout is not None
        for raw_line in self._proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            m = _RCLONE_STATS_RE.search(line)
            if m:
                done_txt, total_txt, pct_txt, rate_txt = m.groups()
                pct = min(100, int(pct_txt))
                if pct != last_emit:
                    self.progress_changed.emit(pct)
                    last_emit = pct
                    self.detail_changed.emit(f"{done_txt} de {total_txt}   ·   {rate_txt}")
                    self.bytes_changed.emit(_parse_size(done_txt), _parse_size(total_txt))
            else:
                self.log_line.emit(line)

        return self._proc.wait()
