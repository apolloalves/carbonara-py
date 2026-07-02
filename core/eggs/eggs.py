from __future__ import annotations

import os
import signal
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

# ── Caminhos e devices fixos (a .iso precisa ir direto para o pendrive Ventoy) ──

EGGS_DIRECTORY = Path("/home/eggs")
FILEPATH = Path("/home/eggs/.mnt")
VENTOY = Path("/mnt/VENTOY")
MDSATA = Path("/mnt/MDSATA")
MDSATA_EGGS = MDSATA / "ARCHEGGS"

VENTOY_DEVICE = "/dev/sdd1"
MDSATA_DEVICE = "/dev/sdd3"


def _safe_remove_eggs_dir() -> None:
    """Desmonta todos os bind mounts dentro de /home/eggs antes de remover o diretório."""
    if not EGGS_DIRECTORY.exists():
        return

    # Lê /proc/mounts e desmonta em ordem reversa (mais profundo primeiro)
    try:
        with open("/proc/mounts") as f:
            mounts = [
                line.split()[1]
                for line in f
                if line.split()[1].startswith(str(EGGS_DIRECTORY))
            ]
        for mount in sorted(mounts, reverse=True):
            subprocess.run(
                ["umount", "-lf", mount],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass

    shutil.rmtree(str(EGGS_DIRECTORY), ignore_errors=True)


def require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("Este módulo precisa ser executado como root.")


def _is_mountpoint(path: Path) -> bool:
    result = subprocess.run(
        ["mountpoint", "-q", str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode == 0


def ensure_mounted(device: str, mountpoint: Path) -> None:
    mountpoint.mkdir(parents=True, exist_ok=True)
    if not _is_mountpoint(mountpoint):
        result = subprocess.run(
            ["mount", device, str(mountpoint)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Falha ao montar {device} em {mountpoint}: {result.stderr.strip()}"
            )


def find_iso_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(path.glob("*.iso"))


# ── Worker genérico (não-rsync) — streama stdout linha a linha ─────────────────

class ShellWorker(QThread):
    """Executa um comando e transmite stdout/stderr linha a linha.

    Implementa a mesma interface de sinais usada pelo RsyncWorker
    (progress_changed, status_changed, file_changed, log_line,
    finished_ok, failed), para plugar diretamente no BackupProgressDialog.
    """

    progress_changed = Signal(int)
    status_changed = Signal(str)
    file_changed = Signal(str)
    log_line = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, cmd: list[str], title: str = "", cwd: str | None = None, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.title = title
        self.cwd = cwd
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                import os, signal
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                self._proc.kill()
            # Limpa o que o eggs produce criou, desmontando mounts antes
            _safe_remove_eggs_dir()

    def run(self) -> None:
        try:
            if self.title:
                self.status_changed.emit(self.title)

            self._proc = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid,   # cria grupo próprio — killpg mata tudo
            )

            assert self._proc.stdout is not None
            for raw_line in self._proc.stdout:
                line = raw_line.rstrip("\n")
                if not line:
                    continue
                self.log_line.emit(line)
                self.file_changed.emit(line[:140])

            self._proc.wait()

            if self._cancelled:
                self.failed.emit("Operação cancelada.")
                return

            if self._proc.returncode != 0:
                self.failed.emit(f"exit code {self._proc.returncode}")
                return

            self.finished_ok.emit()

        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


def _run_step(dialog, cmd: list[str]) -> bool:
    """Executa um passo síncrono e rápido (mv, rsync curto, mkdir...)."""
    dialog.append_log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.splitlines():
            dialog.append_log(line)
    if result.returncode != 0:
        dialog.append_log(f"ERRO: {result.stderr.strip()}")
        return False
    return True


def _cleanup_iso(dialog) -> None:
    """Remove todos os .iso do FILEPATH após uma falha — evita lixo ocupando espaço."""
    try:
        removed = list(FILEPATH.glob("*.iso"))
        for f in removed:
            f.unlink(missing_ok=True)
            dialog.append_log(f"Removido: {f}")
        if removed:
            dialog.append_log(f"--- {len(removed)} arquivo(s) removido(s) de {FILEPATH} ---")
    except Exception as exc:  # noqa: BLE001
        dialog.append_log(f"AVISO: não foi possível limpar {FILEPATH}: {exc}")


def _move_and_backup_iso(dialog, iso_files: list[Path]) -> bool:
    date_str = datetime.now().strftime("%Y-%m-%d")
    src = iso_files[0]
    renamed = FILEPATH / f"ARCHLINUX_{date_str}.iso"

    dialog.set_status("Renomeando arquivo .iso...")
    dialog.append_log(f"Copiando: {src} -> {renamed}")
    try:
        src.rename(renamed)
    except OSError as exc:
        dialog.append_log(f"ERRO ao renomear: {exc}")
        _cleanup_iso(dialog)
        return False

    dialog.set_status(f"Movendo para {VENTOY}...")
    dialog.set_current_file(str(renamed))
    if not _run_step(dialog, ["mv", "-v", str(renamed), str(VENTOY)]):
        dialog.append_log("Falha ao mover ISO para o Ventoy — limpando arquivo gerado...")
        _cleanup_iso(dialog)
        return False

    dest = VENTOY / renamed.name

    dialog.set_status(f"Fazendo backup em {MDSATA_EGGS}...")
    dialog.set_current_file(str(dest))
    MDSATA_EGGS.mkdir(parents=True, exist_ok=True)
    if not _run_step(dialog, ["rsync", "-avh", "--progress", str(dest), f"{MDSATA_EGGS}/"]):
        dialog.append_log("AVISO: backup no MDSATA falhou, mas ISO já está no Ventoy.")
        # ISO no Ventoy já está ok — não remove
        return False

    dialog.append_log(f"--- arquivo '{dest.name}' pronto no Ventoy e no MDSATA ---")
    return True


def _finish(dialog, ok: bool, success_msg: str, fail_msg: str) -> None:
    dialog.set_current_file("—")
    dialog.progress.setRange(0, 100)
    dialog.progress.setValue(100 if ok else 0)
    dialog.set_status(success_msg if ok else fail_msg)
    dialog.set_running(False)
    dialog.btn_close.setEnabled(True)


# ── Ações principais ────────────────────────────────────────────────────────

def _free_gb(path: Path) -> float:
    """Retorna o espaço livre em GB de um mountpoint."""
    try:
        st = os.statvfs(str(path))
        return (st.f_bavail * st.f_frsize) / (1024 ** 3)
    except OSError:
        return 0.0


def _used_root_gb() -> float:
    """Retorna o espaço usado em / como estimativa do tamanho da ISO comprimida."""
    try:
        st = os.statvfs("/")
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        # eggs usa zstd -b 1M -X (compressão pesada) — estima ~55% do usado
        return (used / (1024 ** 3)) * 0.55
    except OSError:
        return 0.0


def check_space(dialog) -> bool:
    """
    Verifica se há espaço suficiente no Ventoy e no MDSATA.
    Retorna True se OK, False se algum destino está sem espaço.
    """
    estimated_gb = _used_root_gb()
    ventoy_free = _free_gb(VENTOY) if _is_mountpoint(VENTOY) else 0.0
    mdsata_free = _free_gb(MDSATA_EGGS.parent) if _is_mountpoint(MDSATA) else 0.0

    problems = []

    if ventoy_free < estimated_gb:
        problems.append(
            f"VENTOY ({VENTOY}): {ventoy_free:.1f} GB livres "
            f"— necessário ~{estimated_gb:.1f} GB"
        )
    if mdsata_free < estimated_gb:
        problems.append(
            f"MDSATA ({MDSATA}): {mdsata_free:.1f} GB livres "
            f"— necessário ~{estimated_gb:.1f} GB"
        )

    if problems:
        dialog.append_log("AVISO: Espaço insuficiente nos destinos:")
        for p in problems:
            dialog.append_log(f"  ✗ {p}")
        dialog.append_log(
            f"\nEstimativa de tamanho da ISO: ~{estimated_gb:.1f} GB "
            f"(comprimido, baseado no uso atual de /)"
        )
        dialog.set_status("Espaço insuficiente — verifique os destinos.")
        dialog.progress.setRange(0, 100)
        dialog.progress.setValue(0)
        dialog._had_failure = True   # ← garante que _show_result_inline mostre erro
        dialog.set_running(False)
        return False

    dialog.append_log(
        f"INFO: Espaço verificado: ISO estimada ~{estimated_gb:.1f} GB | "
        f"Ventoy {ventoy_free:.1f} GB livres | MDSATA {mdsata_free:.1f} GB livres"
    )
    return True


def create_eggs(dialog, parent=None) -> None:
    """Cria uma nova ISO via penguins-eggs (ou move uma já existente para o Ventoy)."""
    require_root()

    dialog.set_running(True)
    dialog.progress.setRange(0, 0)
    dialog.set_status("Verificando dispositivos...")
    dialog.set_current_file("—")
    dialog.append_log("=== CREATE PENGUIN'S EGGS ===")

    try:
        ensure_mounted(VENTOY_DEVICE, VENTOY)
        ensure_mounted(MDSATA_DEVICE, MDSATA)
    except Exception as exc:  # noqa: BLE001
        dialog.append_log(f"ERRO: {exc}")
        _finish(dialog, False, "", "Falha ao montar dispositivos.")
        return

    dialog.append_log(f"Limpando: {EGGS_DIRECTORY}")
    _safe_remove_eggs_dir()

    if not check_space(dialog):
        return

    iso_files = find_iso_files(FILEPATH)

    if iso_files:
        dialog.progress.setRange(0, 100)
        ok = _move_and_backup_iso(dialog, iso_files)
        _finish(dialog, ok, "Concluído com sucesso.", "Falha na operação.")
        return

    # Nenhuma iso encontrada — gera uma nova via `eggs produce`
    date_str = datetime.now().strftime("%Y-%m-%d")
    dialog.set_status("Gerando nova ISO (eggs produce)...")
    dialog.append_log("")
    dialog.append_log("INICIANDO: Nenhuma .iso encontrada — gerando nova ISO via eggs produce...")
    dialog.append_log("")

    worker = ShellWorker(
        ["eggs", "produce", "--clone", "--nointeractive", "--prefix=ARCHLINUX", f"--basename=_{date_str}"],
        title="Gerando ISO...",
        parent=dialog,
    )

    register = getattr(dialog, "register_worker", None)
    if callable(register):
        dialog.register_worker(worker)
    else:
        dialog._worker = worker

    worker.log_line.connect(dialog.append_log)
    worker.file_changed.connect(dialog.set_current_file)

    def on_ok() -> None:
        dialog.append_log("--- ISO gerada com sucesso ---")
        dialog.progress.setRange(0, 100)
        new_isos = find_iso_files(FILEPATH)
        if new_isos:
            ok = _move_and_backup_iso(dialog, new_isos)
            _finish(dialog, ok, "Concluído com sucesso.", "Falha na operação.")
        else:
            _finish(dialog, True, "ISO gerada, mas não encontrada para mover.", "")

    def on_fail(msg: str) -> None:
        dialog.append_log(f"ERRO: {msg}")
        _finish(dialog, False, "", "Falha ao gerar ISO.")

    worker.finished_ok.connect(on_ok)
    worker.failed.connect(on_fail)
    worker.start()


def check_eggs(dialog, parent=None) -> None:
    """Verifica se há .iso pendente; move/backup se houver, senão limpa o diretório."""
    require_root()

    dialog.set_running(True)
    dialog.progress.setRange(0, 0)
    dialog.set_status("Verificando dispositivos...")
    dialog.set_current_file("—")
    dialog.append_log("=== CHECK PENGUIN'S EGGS ===")

    try:
        ensure_mounted(VENTOY_DEVICE, VENTOY)
        ensure_mounted(MDSATA_DEVICE, MDSATA)
    except Exception as exc:  # noqa: BLE001
        dialog.append_log(f"ERRO: {exc}")
        _finish(dialog, False, "", "Falha ao montar dispositivos.")
        return

    dialog.progress.setRange(0, 100)
    iso_files = find_iso_files(FILEPATH)

    if iso_files:
        dialog.append_log(f"{len(iso_files)} arquivo(s) .iso encontrado(s) em {FILEPATH}")
        if not check_space(dialog):
            return
        ok = _move_and_backup_iso(dialog, iso_files)
        _finish(dialog, ok, "Concluído com sucesso.", "Falha na operação.")
        return

    dialog.append_log(f"Nenhum .iso encontrado em {FILEPATH}")
    dialog.append_log(f"Limpando: {EGGS_DIRECTORY}")
    _safe_remove_eggs_dir()
    _finish(dialog, True, "Diretório limpo — nada para fazer.", "")


def install_eggs(dialog, parent=None) -> None:
    """Instala o penguins-eggs e o módulo Calamares, se necessário."""
    require_root()

    dialog.set_running(True)
    dialog.progress.setRange(0, 0)
    dialog.set_status("Verificando instalação...")
    dialog.set_current_file("—")
    dialog.append_log("=== INSTALL PENGUIN'S EGGS ===")

    eggs_installed = subprocess.run(
        ["pacman", "-Q", "penguins-eggs"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0

    steps: list[list[str]] = []

    if not eggs_installed:
        dialog.append_log("penguins-eggs não encontrado — será instalado.")
        steps.append([
            "bash", "-c",
            "rm -rf /tmp/get-eggs && "
            "git clone https://github.com/pieroproietti/get-eggs /tmp/get-eggs && "
            "cd /tmp/get-eggs && ./get-eggs.sh",
        ])
    else:
        dialog.append_log("penguins-eggs já instalado — pulando.")

    calamares_installed = subprocess.run(
        ["pacman", "-Q", "calamares-eggs"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0

    if not calamares_installed:
        dialog.append_log("módulo Calamares não encontrado — será instalado.")
        steps.append(["eggs", "calamares", "--install"])
    else:
        dialog.append_log("módulo Calamares já instalado — pulando.")

    if not steps:
        dialog.append_log("Nada a fazer — tudo já instalado.")
        _finish(dialog, True, "Tudo já instalado.", "")
        return

    def run_next(index: int = 0) -> None:
        if index >= len(steps):
            dialog.append_log("--- instalação concluída ---")
            _finish(dialog, True, "Instalação concluída com sucesso.", "")
            return

        cmd = steps[index]
        worker = ShellWorker(cmd, title="Instalando...", parent=dialog)

        register = getattr(dialog, "register_worker", None)
        if callable(register):
            dialog.register_worker(worker)
        else:
            dialog._worker = worker

        worker.log_line.connect(dialog.append_log)
        worker.file_changed.connect(dialog.set_current_file)

        def on_ok() -> None:
            run_next(index + 1)

        def on_fail(msg: str) -> None:
            dialog.append_log(f"ERRO: {msg}")
            _finish(dialog, False, "", "Falha na instalação.")

        worker.finished_ok.connect(on_ok)
        worker.failed.connect(on_fail)
        worker.start()

    run_next(0)


# ── File manager (não precisa de root) ──────────────────────────────────────

def open_file_manager(kind: str = "nautilus") -> None:
    """Abre o diretório de saída final (Ventoy) no file manager escolhido."""
    # Prioridade: VENTOY (destino final da ISO), depois MDSATA_EGGS, depois FILEPATH
    target = None
    for candidate in (VENTOY, MDSATA_EGGS, FILEPATH):
        if _is_mountpoint(candidate.parent if candidate == MDSATA_EGGS else candidate) or candidate.exists():
            try:
                candidate.stat()
                target = candidate
                break
            except PermissionError:
                continue

    if target is None:
        raise RuntimeError("Nenhum diretório de saída acessível encontrado (Ventoy/MDSATA/eggs).")

    if kind == "broot":
        for term in ("gnome-terminal", "kgx", "x-terminal-emulator", "xterm"):
            if shutil.which(term):
                if term == "gnome-terminal":
                    subprocess.Popen([term, "--", "broot", str(target)])
                else:
                    subprocess.Popen([term, "-e", f"broot {target}"])
                return
        subprocess.Popen(["broot", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
