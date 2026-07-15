from __future__ import annotations

import os
import signal
import shutil
import subprocess
import time
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


def get_dashboard_stats() -> dict:
    """Coleta dados leves para o resumo do topo da tela — não exige root."""
    stats = {
        "last_iso": None,
        "ventoy_free_gb": None,
        "ventoy_total_gb": None,
        "ventoy_free_pct": None,
        "ventoy_fs_type": None,
        "eggs_installed": False,
        "eggs_version": None,
    }

    try:
        if VENTOY.exists() and VENTOY.is_mount():
            # Só ISOs geradas pelo próprio Eggs (renomeadas com o prefixo
            # "ARCHLINUX_" em _move_and_backup_iso) — sem isso, uma ISO
            # baixada manualmente do site oficial (ex: archlinux-2026...)
            # podia aparecer como "última ISO" só por ter mtime mais recente,
            # mesmo sem ter nenhuma relação com o Eggs.
            isos = sorted(
                VENTOY.glob("ARCHLINUX_*.iso"),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            if isos:
                stats["last_iso"] = isos[0].name
            # Chama o próprio `df` em vez de calcular por conta própria —
            # garante que os números batem exatamente com o que o usuário
            # vê rodando `df -h` no terminal, sem risco de divergência por
            # arredondamento (GiB vs GB, base de cálculo do %, etc.).
            # -B1 pra pegar bytes exatos (sem o df já arredondar o tamanho),
            # e --output=pcent pega a porcentagem usada calculada pelo
            # próprio df, do jeito que ele calcula (idêntico ao df -h).
            df_result = subprocess.run(
                ["df", "-B1", "--output=size,avail,pcent", str(VENTOY)],
                capture_output=True, text=True,
            )
            lines = df_result.stdout.strip().splitlines()
            if df_result.returncode == 0 and len(lines) >= 2:
                size_str, avail_str, pcent_str = lines[1].split()
                total_bytes = int(size_str)
                avail_bytes = int(avail_str)
                used_pct = int(pcent_str.rstrip("%"))
                stats["ventoy_total_gb"] = total_bytes / (1024 ** 3)
                stats["ventoy_free_gb"] = avail_bytes / (1024 ** 3)
                stats["ventoy_free_pct"] = 100 - used_pct

            # Tipo de sistema de arquivos — mesma fonte que o storage.py
            # usa pro card de destino do Timeshift (/proc/mounts).
            try:
                with open("/proc/mounts", "r", encoding="utf-8") as fh:
                    for line in fh:
                        parts = line.split()
                        if len(parts) >= 3 and parts[1] == str(VENTOY):
                            stats["ventoy_fs_type"] = parts[2]
                            break
            except Exception:
                pass
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["pacman", "-Q", "penguins-eggs"],
            capture_output=True, text=True,
        )
        stats["eggs_installed"] = result.returncode == 0
        if stats["eggs_installed"]:
            # Saída típica: "penguins-eggs 15.3.2-1" — pega só a versão.
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                stats["eggs_version"] = parts[1]
    except Exception:
        pass

    return stats


def check_eggs_update() -> str | None:
    """Verifica se existe atualização disponível pro penguins-eggs via AUR
    (usando paru). Faz uma chamada de rede — por isso NÃO deve ser chamada
    no auto-refresh periódico da tela, só na abertura da página ou depois
    de uma instalação/atualização. Retorna a versão nova disponível, ou
    None se já está atualizado (ou se não foi possível checar)."""
    try:
        result = subprocess.run(
            ["paru", "-Qua"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            # Formato típico: "penguins-eggs 15.3.2-1 -> 15.4.0-1"
            if line.startswith("penguins-eggs "):
                parts = line.split("->")
                if len(parts) == 2:
                    return parts[1].strip()
        return None
    except Exception:
        return None


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

            # Leitura em chunks — não usar `for line in stdout`, que só quebra
            # em '\n'. Ferramentas como xorriso usam '\r' para atualizar a
            # barra de progresso na mesma linha; sem tratar '\r' também como
            # fim de linha, centenas de atualizações ficam acumuladas numa
            # única string gigante até o próximo '\n' real (só no fim do
            # processo), e emitir isso de uma vez trava o QPlainTextEdit.
            buf = ""
            while True:
                chunk = self._proc.stdout.read(1024)
                if not chunk:
                    break
                buf += chunk
                while True:
                    idx_n = buf.find("\n")
                    idx_r = buf.find("\r")
                    candidates = [i for i in (idx_n, idx_r) if i != -1]
                    if not candidates:
                        break
                    idx = min(candidates)
                    line = buf[:idx].strip()
                    buf = buf[idx + 1:]
                    if not line:
                        continue
                    self.log_line.emit(line)
                    self.file_changed.emit(line[:140])

            leftover = buf.strip()
            if leftover:
                self.log_line.emit(leftover)
                self.file_changed.emit(leftover[:140])

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
        if getattr(dialog, '_cancelled', False) or getattr(worker, '_cancelled', False):
            dialog.set_current_file("—")
            dialog.progress.setRange(0, 100)
            dialog.progress.setValue(0)
            dialog.set_running(False)
            dialog.btn_close.setEnabled(True)
            return
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
    else:
        dialog.append_log("penguins-eggs já instalado — verificando atualização...")

    # No Arch, penguins-eggs está disponível diretamente via chaotic-aur
    # (pacman -Ss penguins-eggs confirma o pacote). Isso é mais confiável
    # que depender do fresh-eggs.sh, que baixa de penguins-eggs.net e
    # atualmente está com a pasta "aur/" vazia/em transição no lado deles
    # (nota oficial do changelog: "Alpine, Arch e Manjaro não estão
    # migrando imediatamente para os novos repositórios"). Tentamos
    # pacman primeiro; se o pacote não existir em nenhum repo configurado,
    # caímos no fresh-eggs.sh como fallback.
    pkg_in_repo = subprocess.run(
        ["pacman", "-Si", "penguins-eggs"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0

    if pkg_in_repo:
        dialog.append_log("penguins-eggs disponível via repo (chaotic-aur) — usando pacman.")
        steps.append(["pacman", "-Sy", "--noconfirm", "--needed", "penguins-eggs"])
    else:
        dialog.append_log(
            "penguins-eggs não encontrado em nenhum repo configurado — "
            "recorrendo ao fresh-eggs.sh (fallback)."
        )
        steps.append([
            "bash", "-c",
            "rm -rf /tmp/get-eggs && "
            "git clone https://github.com/pieroproietti/get-eggs /tmp/get-eggs && "
            "cd /tmp/get-eggs && "
            "SCRIPT=$(ls *.sh 2>/dev/null | grep -iE '^(fresh-eggs|get-eggs)\\.sh$' | head -1) && "
            "if [ -z \"$SCRIPT\" ]; then echo 'ERRO: script de instalação não encontrado no repo get-eggs' >&2; exit 1; fi && "
            "echo \"Executando: $SCRIPT\" && "
            "./\"$SCRIPT\"",
        ])

    calamares_installed = subprocess.run(
        ["pacman", "-Q", "calamares-eggs"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0

    # calamares-eggs não está disponível em nenhum repo pacman (nem
    # chaotic-aur) — só existe via "eggs calamares --install". Por isso,
    # ao contrário do penguins-eggs, não dá pra checar versão disponível
    # antes de rodar. Sempre executamos o comando (ele decide install vs
    # update internamente); senão o módulo nunca seria atualizado depois
    # da primeira instalação.
    if not calamares_installed:
        dialog.append_log("módulo Calamares não encontrado — será instalado.")
    else:
        dialog.append_log("módulo Calamares já instalado — verificando atualização...")
    steps.append(["eggs", "calamares", "--install"])

    def run_next(index: int = 0) -> None:
        if index >= len(steps):
            action = "Atualização" if eggs_installed else "Instalação"
            dialog.append_log(f"--- {action.lower()} concluída ---")
            _finish(dialog, True, f"{action} concluída com sucesso.", "")
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
            if getattr(dialog, '_cancelled', False) or getattr(worker, '_cancelled', False):
                dialog.set_current_file("—")
                dialog.progress.setRange(0, 100)
                dialog.progress.setValue(0)
                dialog.set_running(False)
                dialog.btn_close.setEnabled(True)
                return
            dialog.append_log(f"ERRO: {msg}")
            _finish(dialog, False, "", "Falha na instalação.")

        worker.finished_ok.connect(on_ok)
        worker.failed.connect(on_fail)
        worker.start()

    run_next(0)


# ── File manager (não precisa de root) ──────────────────────────────────────

def resolve_output_target() -> Path:
    """Monta os devices necessários (Ventoy/MDSATA) e retorna o diretório de
    saída acessível, na ordem: Ventoy > MDSATA/ARCHEGGS > FILEPATH.
    Levanta RuntimeError se nenhum estiver acessível."""
    for device, mountpoint in ((MDSATA_DEVICE, MDSATA), (VENTOY_DEVICE, VENTOY)):
        try:
            ensure_mounted(device, mountpoint)
        except Exception:
            pass  # segue com o fallback abaixo (MDSATA/FILEPATH) se não puder montar

    for candidate in (VENTOY, MDSATA_EGGS, FILEPATH):
        if _is_mountpoint(candidate.parent if candidate == MDSATA_EGGS else candidate) or candidate.exists():
            try:
                candidate.stat()
                return candidate
            except PermissionError:
                continue

    raise RuntimeError("Nenhum diretório de saída acessível encontrado (Ventoy/MDSATA/eggs).")


def _bring_window_to_current_workspace(title: str, timeout: float = 2.5) -> None:
    """No X11, move a janela recém-aberta (por título) pro workspace atual e dá foco.
    Sem efeito (silencioso) se xdotool não estiver instalado ou a sessão não for X11."""
    if not shutil.which("xdotool"):
        return

    try:
        cur_desktop = subprocess.run(
            ["xdotool", "get_desktop"], capture_output=True, text=True,
        ).stdout.strip()
    except Exception:
        return

    win_id = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["xdotool", "search", "--name", title],
            capture_output=True, text=True,
        )
        ids = [w for w in result.stdout.split() if w]
        if ids:
            win_id = ids[-1]
            break
        time.sleep(0.15)

    if win_id is None:
        return

    try:
        if cur_desktop:
            subprocess.run(["xdotool", "set_desktop_for_window", win_id, cur_desktop])
        subprocess.run(["xdotool", "windowactivate", win_id])
    except Exception:
        pass


def open_file_manager(kind: str = "nautilus") -> None:
    """Abre o diretório de saída final (Ventoy). Nautilus abre embutido no
    próprio file manager; broot abre num terminal externo (gnome-terminal,
    kgx, etc.), já que embutir de verdade se mostrou instável demais."""
    target = resolve_output_target()

    if kind != "broot":
        subprocess.Popen(["xdg-open", str(target)])
        return

    if not shutil.which("broot"):
        raise RuntimeError("broot não está instalado (ou não está no PATH).")

    broot_cmd_str = " ".join(["broot", "-s", "-p", "-d", "--sort-by-date", f"'{target}'"])
    shell_wrapper = (
        f"{broot_cmd_str}; "
        f'st=$?; if [ $st -ne 0 ]; then echo; echo "broot saiu com erro ($st)."; '
        f'read -p "Pressione enter para fechar..."; fi'
    )
    wrapped_cmd = ["bash", "-c", shell_wrapper]

    term_title = "Carbonara — broot"
    terminals = [
        ("gnome-terminal", ["gnome-terminal", f"--title={term_title}", "--"] + wrapped_cmd),
        ("ptyxis", ["ptyxis", "--"] + wrapped_cmd),
        ("kgx", ["kgx", "-e", " ".join(wrapped_cmd)]),
        ("konsole", ["konsole", "--title", term_title, "-e"] + wrapped_cmd),
        ("xfce4-terminal", ["xfce4-terminal", "-T", term_title, "-e", " ".join(wrapped_cmd)]),
        ("terminator", ["terminator", "-T", term_title, "-e", " ".join(wrapped_cmd)]),
        ("tilix", ["tilix", "-t", term_title, "-e", " ".join(wrapped_cmd)]),
        ("alacritty", ["alacritty", "-t", term_title, "-e"] + wrapped_cmd),
        ("foot", ["foot", "-T", term_title] + wrapped_cmd),
        ("x-terminal-emulator", ["x-terminal-emulator", "-e", " ".join(wrapped_cmd)]),
        ("xterm", ["xterm", "-T", term_title, "-e", " ".join(wrapped_cmd)]),
    ]
    for term, cmd in terminals:
        if shutil.which(term):
            subprocess.Popen(cmd)
            _bring_window_to_current_workspace(term_title)
            return

    raise RuntimeError(
        "Nenhum emulador de terminal encontrado (gnome-terminal, ptyxis, kgx, "
        "konsole, xfce4-terminal, terminator, tilix, alacritty, foot, xterm). "
        "Instale um deles para usar o broot."
    )
