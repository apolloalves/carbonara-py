from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

# pv -n emite só o número da porcentagem (0-100) por linha no stderr —
# mesmo estilo de parsing incremental já usado pro xorriso do Eggs.
_PV_PERCENT_RE = re.compile(r"^\s*(\d{1,3})\s*$")


class ClonezillaCompressWorker(QThread):
    """Comprime uma pasta de imagem Clonezilla em .tar.zst via
    `tar | pv -n | zstd`, com progresso real (0-100%) a partir dos bytes
    lidos da pasta de origem (medidos pelo pv).

    Substitui a função `compress()` do .bashrc (tar -cvf ... zstd), trocando
    o -v (listagem de arquivos) por progresso percentual real via pv —
    mesma ideia, saída mais útil numa barra de progresso.

    Interface de sinais compatível com RsyncWorker (progress_changed,
    status_changed, log_line, finished_ok, failed), para plugar direto
    nos mesmos dialogs de progresso (BackupProgressDialog) já usados
    pelo resto do app.
    """

    progress_changed = Signal(int)
    status_changed = Signal(str)
    detail_changed = Signal(str)
    tree_ready = Signal(list)
    file_done = Signal(str)
    log_line = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, raw_path: Path, archive_path: Path, parent=None):
        super().__init__(parent)
        self.raw_path = Path(raw_path)
        self.archive_path = Path(archive_path)
        self._proc: subprocess.Popen | None = None
        self._cancelled = False
        self._total_bytes = 0
        self._start_time = 0.0

    def kill(self) -> None:
        """Chamado por BackupProgressDialog._do_cancel() ao cancelar —
        precisa se chamar exatamente `kill()` (não `cancel()`), é esse o
        nome que o dialog espera em todo worker registrado. Mata o grupo
        de processos inteiro (bash + tar + pv + zstd), não só o bash pai,
        senão o pipeline sobrevive rodando escondido."""
        self._cancelled = True
        if self._proc is not None:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    # Alias por clareza/compatibilidade — kill() é o nome real usado pelo
    # dialog, mas cancel() é o verbo mais óbvio pra quem for ler o código.
    cancel = kill

    def run(self) -> None:
        import time

        try:
            self.status_changed.emit(f"Calculando tamanho de {self.raw_path.name}...")
            total_bytes = self._folder_size_bytes(self.raw_path)
            self._total_bytes = total_bytes
            self.log_line.emit(
                f"Tamanho de origem: {total_bytes / (1024 ** 3):.2f} GB"
            )

            self.status_changed.emit(f"Comprimindo {self.raw_path.name}...")
            self._start_time = time.monotonic()

            self.tree_ready.emit(self._build_relative_paths())

            # -v faz o tar listar cada arquivo conforme processa — como o
            # archive vai pro stdout (-f -), o GNU tar manda essa listagem
            # pro stderr automaticamente (não corrompe o stream de dados).
            cmd = (
                f"tar -cvf - -C {shlex.quote(str(self.raw_path.parent))} "
                f"{shlex.quote(self.raw_path.name)} "
                f"| pv -n -s {total_bytes} "
                f"| zstd -T0 --ultra -22 --long=31 -o "
                f"{shlex.quote(str(self.archive_path))}"
            )
            self.log_line.emit(f"$ {cmd}")

            self._proc = subprocess.Popen(
                ["bash", "-c", cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid,
            )

            last_emit = -1
            assert self._proc.stderr is not None
            for raw_line in self._proc.stderr:
                # pv com -n manda cada atualização como uma linha própria
                # terminada em \n (sem \r), então dá pra iterar normal.
                line = raw_line.strip()
                if not line:
                    continue
                m = _PV_PERCENT_RE.match(line)
                if m:
                    pct = min(100, int(m.group(1)))
                    if pct != last_emit:
                        self.progress_changed.emit(pct)
                        last_emit = pct

                        done_bytes = self._total_bytes * pct / 100
                        elapsed = max(time.monotonic() - self._start_time, 0.001)
                        rate_mb_s = (done_bytes / (1024 ** 2)) / elapsed
                        self.detail_changed.emit(
                            f"{done_bytes / 1024 ** 3:.1f} GB de "
                            f"{self._total_bytes / 1024 ** 3:.1f} GB   ·   "
                            f"{rate_mb_s:.1f} MB/s"
                        )
                else:
                    # Linha do tar -v (caminho relativo do arquivo já
                    # escrito no archive) — atualiza a árvore em vez de
                    # inundar o log com uma linha por arquivo.
                    self.file_done.emit(line)

            rc = self._proc.wait()

            if self._cancelled:
                self._remove_partial_archive()
                self.failed.emit("Compressão cancelada pelo usuário.")
                return

            if rc != 0:
                self._remove_partial_archive()
                self.failed.emit(f"tar/pv/zstd terminou com código {rc}.")
                return

            try:
                final_size = self.archive_path.stat().st_size
                self.log_line.emit(
                    f"✓ Arquivo criado: {self.archive_path} "
                    f"({final_size / (1024 ** 3):.2f} GB)"
                )
            except OSError:
                self.log_line.emit(f"✓ Arquivo criado: {self.archive_path}")

            self.finished_ok.emit()

        except Exception as exc:
            self.failed.emit(str(exc))

    @staticmethod
    def _folder_size_bytes(path: Path) -> int:
        result = subprocess.run(
            ["du", "-sb", str(path)],
            capture_output=True, text=True, check=True,
        )
        return int(result.stdout.split()[0])

    def _build_relative_paths(self) -> list:
        """Monta a lista de caminhos relativos (prefixados pelo nome da
        pasta, igual ao que o `tar -v` vai listar) — usada pra montar a
        árvore 'Transferindo:' antes da compressão começar."""
        paths: list[str] = []
        root_name = self.raw_path.name
        parent = self.raw_path.parent
        for dirpath, dirnames, filenames in os.walk(self.raw_path):
            dirnames.sort()
            rel_dir = os.path.relpath(dirpath, parent)
            for f in sorted(filenames):
                paths.append(f"{rel_dir}/{f}")
        return paths

    def _remove_partial_archive(self) -> None:
        """Apaga o .tar.zst incompleto deixado por um cancelamento/falha —
        sem isso, o arquivo quebrado (às vezes 0 bytes) fica pra trás e
        engana a próxima varredura, fazendo o backup parecer 'já
        comprimido' quando na verdade precisa ser refeito."""
        try:
            if self.archive_path.exists():
                self.archive_path.unlink()
                self.log_line.emit(f"Arquivo incompleto removido: {self.archive_path}")
        except OSError as exc:
            self.log_line.emit(f"AVISO: não foi possível remover arquivo incompleto: {exc}")
