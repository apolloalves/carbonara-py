from __future__ import annotations

import os
import re
import signal
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.i18n import tr

# ── Caminhos e devices fixos (a .iso precisa ir direto para o pendrive Ventoy) ──

EGGS_DIRECTORY = Path("/home/eggs")
FILEPATH = Path("/home/eggs/.mnt")
VENTOY = Path("/mnt/VENTOY")
MDSATA = Path("/mnt/MDSATA")
MDSATA_EGGS = MDSATA / "ARCHEGGS"

VENTOY_DEVICE = "/dev/sdd1"
MDSATA_DEVICE = "/dev/sdd3"


def get_disk_stats(mountpoint: str) -> dict:
    """Generaliza a checagem de espaço que get_dashboard_stats fazia só
    pro Ventoy — usado pelo card de destino dinâmico na UI, que agora
    mostra stats de qualquer disco escolhido no combo, não só o Ventoy.
    Mesma fonte (`df`) que garante bater com `df -h` no terminal."""
    result = {"free_gb": None, "total_gb": None, "free_pct": None, "fs_type": None}
    path = Path(mountpoint)
    if not path.exists() or not path.is_mount():
        return result

    df_result = subprocess.run(
        ["df", "-B1", "--output=size,avail,pcent", str(path)],
        capture_output=True, text=True,
    )
    lines = df_result.stdout.strip().splitlines()
    if df_result.returncode == 0 and len(lines) >= 2:
        size_str, avail_str, pcent_str = lines[1].split()
        total_bytes = int(size_str)
        avail_bytes = int(avail_str)
        used_pct = int(pcent_str.rstrip("%"))
        result["total_gb"] = total_bytes / (1024 ** 3)
        result["free_gb"] = avail_bytes / (1024 ** 3)
        result["free_pct"] = 100 - used_pct

    try:
        with open("/proc/mounts", "r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == str(path):
                    result["fs_type"] = parts[2]
                    break
    except Exception:
        pass

    return result


def get_last_iso_for(directory: str) -> dict:
    """Última ISO ARCHLINUX_*.iso dentro de um diretório específico —
    generaliza o que get_dashboard_stats fazia só pro Ventoy, pro card
    'ÚLTIMA ISO' acompanhar o disco escolhido no combo.

    Quando o disco escolhido é o MDSATA, o Eggs guarda a ISO numa
    subpasta fixa (MDSATA_EGGS = MDSATA/ARCHEGGS) — sem esse resolver, o
    card checava a raiz do disco e dizia "sem ISO" mesmo com uma ISO
    salva ali dentro (list_existing_isos já sabia disso; esse aqui não
    sabia, causando a divergência)."""
    result = {"name": None, "date_str": None, "size_gb": None}
    path = Path(directory)
    if path == MDSATA:
        path = MDSATA_EGGS
    if not path.exists():
        return result

    isos = sorted(path.glob("ARCHLINUX_*.iso"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not isos:
        return result

    st = isos[0].stat()
    result["name"] = isos[0].name
    result["date_str"] = datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")
    result["size_gb"] = st.st_size / (1024 ** 3)
    return result


def get_dashboard_stats() -> dict:
    """Coleta dados leves para o resumo do topo da tela — não exige root."""
    stats = {
        "last_iso": None,
        "last_iso_date": None,
        "last_iso_size_gb": None,
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
                _iso_stat = isos[0].stat()
                # st_mtime como proxy de "data de criação": a ISO não é
                # reescrita depois de gerada (só renomeada/movida em
                # _move_and_backup_iso), então mtime reflete o momento
                # real da geração. Linux não tem um "creation time"
                # confiável e portável como o Windows/macOS têm.
                stats["last_iso_date"] = datetime.fromtimestamp(_iso_stat.st_mtime).strftime("%d/%m/%Y %H:%M")
                stats["last_iso_size_gb"] = _iso_stat.st_size / (1024 ** 3)
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
    """Verifica se existe atualização disponível pro penguins-eggs.

    Checa DOIS caminhos possíveis, porque o pacote já migrou de lugar
    antes e pode migrar de novo:
      1. Repositório normal (ex: chaotic-aur configurado como repo) —
         via `checkupdates` (pacman-contrib), que consulta um cache
         local da base de dados sem precisar de root nem alterar nada.
      2. AUR de verdade (pacote "estrangeiro") — via `paru -Qua`, como
         antes.
    O bug real encontrado: quando o pacote passou a vir do repo (não
    mais do AUR), só o checkpoint 1 acima existia, então a tela sempre
    dizia "sem atualização" mesmo quando tinha — `paru -Qua` nunca
    lista pacotes que não são mais "estrangeiros".

    Faz chamada de rede — por isso NÃO deve ser chamada no auto-refresh
    periódico da tela, só na abertura da página ou depois de uma
    instalação/atualização. Retorna a versão nova disponível, ou None
    se já está atualizado (ou se não foi possível checar por nenhum
    dos dois caminhos)."""
    # 1. Repositório normal (pacman-contrib)
    try:
        result = subprocess.run(
            ["checkupdates"],
            capture_output=True, text=True, timeout=20,
        )
        # checkupdates devolve 2 quando não há NENHUMA atualização (não é
        # erro) — só trata como falha de verdade se não achar nem stdout
        if result.returncode in (0, 2):
            for line in result.stdout.splitlines():
                # Formato: "penguins-eggs 15.3.2-1 -> 15.4.0-1"
                if line.startswith("penguins-eggs "):
                    parts = line.split("->")
                    if len(parts) == 2:
                        return parts[1].strip()
    except Exception:
        pass

    # 2. AUR de verdade (pacote estrangeiro)
    try:
        result = subprocess.run(
            ["paru", "-Qua"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("penguins-eggs "):
                    parts = line.split("->")
                    if len(parts) == 2:
                        return parts[1].strip()
    except Exception:
        pass

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
    # Ignora symlinks órfãos: o eggs cria um link em EGGS_DIRECTORY
    # apontando pro arquivo físico em EGGS_DIRECTORY/mnt (ln -s), e
    # _move_and_backup_iso resolve e move só o arquivo real. Se esse link
    # sobreviver de uma tentativa anterior (já movido embora), ele ainda
    # bate no glob mas aponta pro nada — sem esse filtro, cada tentativa
    # nova "encontrava" uma ISO fantasma que já tinha ido pro destino há
    # muito tempo.
    return sorted(
        p for p in path.glob("*.iso")
        if not p.is_symlink() or p.resolve().exists()
    )


@dataclass(frozen=True)
class IsoEntry:
    path: Path
    name: str
    date_str: str
    size_gb: float


def list_existing_isos(directories: list[Path] | None = None) -> list[IsoEntry]:
    """Lista todas as ISOs já geradas (padrão ARCHLINUX_*.iso) nos
    diretórios de destino informados — usado pela listagem estilo
    Timeshift na tela do Eggs. Por padrão, olha em VENTOY e MDSATA_EGGS
    (os dois destinos reais usados hoje)."""
    dirs = directories or [VENTOY, MDSATA_EGGS]
    entries: list[IsoEntry] = []
    seen: set[Path] = set()
    for directory in dirs:
        if not directory.exists():
            continue
        for iso_path in sorted(directory.glob("ARCHLINUX_*.iso")):
            resolved = iso_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                st = iso_path.stat()
            except OSError:
                continue
            entries.append(IsoEntry(
                path=iso_path,
                name=iso_path.name,
                date_str=datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M"),
                size_gb=st.st_size / (1024 ** 3),
            ))
    entries.sort(key=lambda e: e.path.stat().st_mtime, reverse=True)
    return entries


def _find_produced_iso() -> list[Path]:
    """Procura a ISO recém-gerada pelo `eggs produce`.

    Confirmado direto na fonte do penguins-eggs-legacy (settings.ts):
        snapshot_mnt = path.join(snapshot_dir, 'mnt/')
    e xorriso-command.ts escreve em `snapshot_mnt + isoFilename`. Com
    snapshot_dir default = '/home/eggs', o destino real é
    "/home/eggs/mnt/<arquivo>.iso" — SEM ponto, subpasta "mnt", não a
    raiz de EGGS_DIRECTORY nem FILEPATH ("/home/eggs/.mnt", com ponto).

    A mensagem final do próprio eggs ("in the nest: /home/eggs.") é
    enganosa: ela imprime `snapshot_dir`, não `snapshot_mnt` — por isso
    parece que o arquivo está na raiz, mas na verdade está um nível
    mais fundo. Checamos EGGS_DIRECTORY/mnt primeiro (local real
    confirmado), depois a raiz e FILEPATH como fallback (por segurança,
    caso a config do usuário customize snapshot_dir de outro jeito).
    """
    for candidate in (EGGS_DIRECTORY / "mnt", EGGS_DIRECTORY, FILEPATH):
        found = find_iso_files(candidate)
        if found:
            return found
    return []


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

    def __init__(self, cmd: list[str], title: str = "", cwd: str | None = None,
                 suppress_patterns: list[str] | None = None,
                 progress_pattern: str = r"(\d+(?:\.\d+)?)\s*%\s*done",
                 progress_only: bool = False, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.title = title
        self.cwd = cwd
        self._proc: subprocess.Popen | None = None
        self._cancelled = False
        # Linhas de log que são ruído cosmético conhecido e não indicam
        # falha real (ex.: o `eggs calamares --install` tenta `pacman -S
        # calamares` mesmo quando `calamares-eggs` já supre a necessidade,
        # falha, mas segue em frente normalmente). Usado apenas quando o
        # chamador sabe explicitamente que essas linhas são inofensivas
        # NESSE comando específico — não filtra nada por padrão.
        self._suppress_patterns = suppress_patterns or []
        # Padrão pra extrair percentual real de progresso — default é o
        # formato do xorriso ("XX.XX% done"). rsync usa outro formato
        # ("XX%" solto entre bytes/velocidade/ETA), então quem cria o
        # worker pra um rsync passa um padrão diferente.
        self._progress_pattern = progress_pattern
        # Quando True, NENHUMA linha crua vai pro log — só o percentual
        # extraído alimenta a barra. Existe porque o rsync --progress
        # solta uma linha por segundo, cheia de bytes/velocidade/ETA que
        # ninguém lê de verdade; a barra já conta a história toda.
        self._progress_only = progress_only

    def _is_suppressed(self, line: str) -> bool:
        return any(pattern in line for pattern in self._suppress_patterns)

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
            last_progress_emit = 0.0
            MIN_PROGRESS_INTERVAL = 0.15  # segundos
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
                    if self._is_suppressed(line):
                        continue
                    # Extrai o percentual real de linhas tipo
                    # "xorriso : UPDATE :  88.90% done, ..." — sem isso, a
                    # barra ficava no modo indeterminado (só andando de um
                    # lado pro outro) e o número real ficava enterrado no
                    # log rolando, difícil de ver em qual etapa travou.
                    match = re.search(self._progress_pattern, line)
                    if match:
                        # O xorriso dispara MUITAS dessas linhas por segundo
                        # nas fases finais (visto ao vivo: mesma % repetida
                        # 3-4x seguidas). Emitir cada uma sinaliza pra thread
                        # principal renderizar log+barra a cada uma — numa
                        # rajada, isso inunda a fila de eventos do Qt mais
                        # rápido do que ela consegue desenhar, e a UI trava
                        # de verdade (não é só aparência), acionando o
                        # "Not Responding" do compositor. Mesmo padrão do
                        # buffer de 300ms já usado em backup_progress.py
                        # pro rsync — aqui throttlando só as linhas de %.
                        now = time.monotonic()
                        if now - last_progress_emit < MIN_PROGRESS_INTERVAL:
                            continue
                        last_progress_emit = now
                        try:
                            self.progress_changed.emit(int(float(match.group(1))))
                        except ValueError:
                            pass
                        if self._progress_only:
                            continue
                    elif self._progress_only:
                        # Modo "só progresso": nem essa linha nem nenhuma
                        # outra crua vai pro log — a barra já conta a
                        # história (usado no rsync de backup pro MDSATA,
                        # que solta uma linha de bytes/velocidade/ETA por
                        # segundo que ninguém lê de verdade).
                        continue
                    self.log_line.emit(line)
                    self.file_changed.emit(line[:140])

            leftover = buf.strip()
            if leftover and not self._is_suppressed(leftover) and not self._progress_only:
                self.log_line.emit(leftover)
                self.file_changed.emit(leftover[:140])

            self._proc.wait()

            if self._cancelled:
                self.failed.emit(tr("eggs_core.op_cancelled"))
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
        dialog.append_log(tr("eggs_core.log_error_prefix").format(msg=result.stderr.strip()))
        return False
    return True


def _cleanup_iso(dialog) -> None:
    """Remove todos os .iso de EGGS_DIRECTORY/mnt (path real), EGGS_DIRECTORY
    e FILEPATH após uma falha — evita lixo ocupando espaço, em qualquer um
    dos locais possíveis."""
    for directory in (EGGS_DIRECTORY / "mnt", EGGS_DIRECTORY, FILEPATH):
        try:
            removed = list(directory.glob("*.iso"))
            for f in removed:
                f.unlink(missing_ok=True)
                dialog.append_log(tr("eggs_core.log_removed").format(file=f))
            if removed:
                dialog.append_log(tr("eggs_core.log_removed_count").format(count=len(removed), directory=directory))
        except Exception as exc:  # noqa: BLE001
            dialog.append_log(tr("eggs_core.log_cleanup_warning").format(directory=directory, exc=exc))


def _start_move_and_backup(dialog, iso_files: list[Path], destination: Path | None, on_done) -> None:
    """Versão assíncrona do move+backup da ISO.

    A versão antiga (_move_and_backup_iso) rodava shutil.move + rsync —
    potencialmente vários GB — de forma SÍNCRONA dentro de on_ok(), que
    por sua vez é um slot conectado a um sinal cross-thread e por isso
    roda na THREAD PRINCIPAL. Isso travava a UI de verdade bem no
    momento em que o xorriso terminava (visto ao vivo: log mostrando
    "Writing ... completed successfully" e o timer do diálogo parado
    logo em seguida) — o oposto do que resolvemos pro próprio xorriso.
    Agora os passos pesados (mv, rsync) rodam via ShellWorker (thread
    separada), encadeados, chamando on_done(ok) só no final."""
    dest_dir = destination or VENTOY
    date_str = datetime.now().strftime("%Y-%m-%d")
    original = iso_files[0]
    src = original

    # O eggs cria um SYMLINK em EGGS_DIRECTORY apontando pro arquivo real
    # em EGGS_DIRECTORY/mnt (confirmado em make-iso.ts: "ln -s"). Se src
    # for esse link, resolve pro arquivo físico de verdade antes de mover
    # — mover o link em si não adianta nada (o destino precisa dos bytes).
    # Isso é rápido (só resolução de path, sem I/O pesado) — pode ficar
    # síncrono na thread principal sem problema.
    if src.is_symlink():
        real_src = Path(os.path.realpath(src))
        if not real_src.exists():
            dialog.append_log(tr("eggs_core.log_broken_symlink").format(src=src, real_src=real_src))
            _cleanup_iso(dialog)
            on_done(False)
            return
        src = real_src

    renamed_name = f"ARCHLINUX_{date_str}.iso"
    dest = dest_dir / renamed_name

    dialog.set_status(tr("eggs_core.status_moving_to").format(dest_dir=dest_dir))
    dialog.set_current_file(str(src))
    dialog.append_log(tr("eggs_core.log_moving").format(src=src, dest=dest))

    mv_worker = ShellWorker(["mv", str(src), str(dest)], title="Movendo...", parent=dialog)
    dialog.register_worker(mv_worker)
    mv_worker.log_line.connect(dialog.append_log)

    def on_mv_ok() -> None:
        # O symlink original (em EGGS_DIRECTORY) agora aponta pro nada, já
        # que o arquivo real acabou de ser movido embora — sem apagar ele
        # aqui, ele sobrevive e "engana" find_iso_files() numa tentativa
        # futura, fazendo o Carbonara achar que ainda existe uma ISO
        # pronta pra mover.
        if original != src and original.is_symlink():
            original.unlink(missing_ok=True)

        dialog.append_log(tr("eggs_core.log_iso_created").format(name=dest.name))
        dialog.set_status(tr("eggs_core.status_backing_up").format(path=MDSATA_EGGS))
        dialog.set_current_file(str(dest))
        dialog.append_log(tr("eggs_core.log_backup_start").format(path=MDSATA_EGGS))
        MDSATA_EGGS.mkdir(parents=True, exist_ok=True)

        rsync_worker = ShellWorker(
            ["rsync", "-avh", "--progress", str(dest), f"{MDSATA_EGGS}/"],
            title="Copiando para MDSATA...",
            progress_pattern=r"(\d{1,3})%",
            progress_only=True,
            parent=dialog,
        )
        dialog.register_worker(rsync_worker)
        rsync_worker.progress_changed.connect(dialog.set_progress_percent)

        def on_rsync_ok() -> None:
            dialog.append_log(tr("eggs_core.log_ready_both").format(name=dest.name))
            on_done(True)

        def on_rsync_fail(msg: str) -> None:
            dialog.append_log(tr("eggs_core.log_backup_failed_ventoy_ok").format(msg=msg))
            # ISO no Ventoy já está ok — não remove
            on_done(False)

        rsync_worker.finished_ok.connect(on_rsync_ok)
        rsync_worker.failed.connect(on_rsync_fail)
        rsync_worker.start()

    def on_mv_fail(msg: str) -> None:
        dialog.append_log(tr("eggs_core.log_move_error").format(dest_dir=dest_dir, msg=msg))
        _cleanup_iso(dialog)
        on_done(False)

    mv_worker.finished_ok.connect(on_mv_ok)
    mv_worker.failed.connect(on_mv_fail)
    mv_worker.start()


def _finish(dialog, ok: bool, success_msg: str, fail_msg: str) -> None:
    dialog.set_current_file("—")
    dialog.progress.setRange(0, 100)
    if ok:
        dialog.progress.setValue(100)
    # Em falha, NÃO zera — deixa a barra parada no último percentual
    # real recebido (ex: 88%), pra ficar visível de cara em qual etapa
    # travou, sem precisar rolar o log procurando a última linha.
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


def _fail_space_check(dialog, message: str) -> None:
    dialog.set_status(message)
    dialog.progress.setRange(0, 100)
    dialog.progress.setValue(0)
    dialog._had_failure = True   # ← garante que _show_result_inline mostre erro
    dialog.set_running(False)


def check_space(dialog, destination: Path | None = None) -> Path | None:
    """
    Verifica se há espaço suficiente no destino escolhido e no MDSATA
    (backup, sempre fixo). Se o destino escolhido não tiver espaço,
    sugere discos alternativos com espaço suficiente diretamente na
    mesma janela (EggsProgressDialog.prompt_alternative_destination) —
    se o usuário escolher um, a checagem é refeita com o novo destino.

    Retorna o Path do destino final (pode ter mudado se o usuário
    escolheu uma alternativa), ou None se não há espaço em algum lugar
    sem alternativa viável, ou o usuário cancelou a escolha.
    """
    dest = destination or VENTOY
    estimated_gb = _used_root_gb()
    mdsata_free = _free_gb(MDSATA_EGGS.parent) if _is_mountpoint(MDSATA) else 0.0

    # MDSATA é o backup fixo (não escolhido pelo usuário) — sem espaço
    # ali não tem "alternativa" que faça sentido sugerir, é só falha.
    if mdsata_free < estimated_gb:
        dialog.append_log(tr("eggs_core.log_space_insufficient_header"))
        dialog.append_log(tr("eggs_core.log_space_mdsata_detail").format(path=MDSATA, free=mdsata_free, needed=estimated_gb))
        dialog.append_log(tr("eggs_core.log_space_estimate").format(gb=estimated_gb))
        _fail_space_check(dialog, tr("eggs_core.status_space_mdsata_fail"))
        return None

    dest_free = _free_gb(dest) if _is_mountpoint(dest) else 0.0
    if dest_free >= estimated_gb:
        dialog.append_log(tr("eggs_core.log_space_ok").format(gb=estimated_gb, dest=dest, dest_free=dest_free, mdsata_free=mdsata_free))
        return dest

    # Destino escolhido sem espaço — procura alternativas antes de desistir.
    dialog.append_log(tr("eggs_core.log_space_dest_insufficient").format(dest=dest, free=dest_free, needed=estimated_gb))

    from core.system.disks import list_relevant_disks, parse_size_to_gb

    candidates = []
    for d in list_relevant_disks():
        if d.mountpoint == str(dest):
            continue
        free_gb = parse_size_to_gb(d.avail)
        if free_gb >= estimated_gb:
            candidates.append({
                "mountpoint": d.mountpoint,
                "free_gb": free_gb,
                "label": d.model or d.name,
            })

    if not candidates:
        dialog.append_log(tr("eggs_core.log_no_alt_disk"))
        _fail_space_check(dialog, tr("eggs_core.status_space_fail"))
        return None

    dialog.append_log(tr("eggs_core.log_suggesting_alt").format(count=len(candidates)))
    chosen = dialog.prompt_alternative_destination(candidates, estimated_gb)

    if not chosen:
        dialog.append_log(tr("eggs_core.log_no_alt_chosen"))
        _fail_space_check(dialog, tr("eggs_core.status_user_cancelled"))
        return None

    dialog.append_log(tr("eggs_core.log_new_dest_chosen").format(chosen=chosen))
    return check_space(dialog, Path(chosen))


def create_eggs(dialog, parent=None, destination: str | None = None, update_check_version: str | None = None) -> None:
    """Cria uma nova ISO via penguins-eggs (ou move uma já existente para o
    destino escolhido). `destination` é o path de um disco/mount escolhido
    na UI (ver core/system/disks.py) — se None, usa VENTOY por padrão.

    `update_check_version` vem da checagem de update que a UI já fez
    ANTES de abrir esse diálogo (self._last_update_version em
    eggs_page.py) — não checa de novo aqui pra não duplicar a chamada de
    rede. Só serve pra deixar explícito no log inicial que a checagem
    aconteceu, mesmo quando não havia nada pra atualizar."""
    require_root()

    dest_dir = Path(destination) if destination else VENTOY

    dialog.set_running(True)
    dialog.progress.setRange(0, 0)
    dialog.set_status(tr("eggs_core.status_checking_devices"))
    dialog.set_current_file("—")
    dialog.append_log(tr("eggs_core.log_header_create"))
    dialog.append_log(tr("eggs_core.log_dest_chosen").format(dest_dir=dest_dir))
    if update_check_version:
        dialog.append_log(tr("eggs_core.log_updated_before_build").format(version=update_check_version))
    else:
        dialog.append_log(tr("eggs_core.log_already_latest"))

    try:
        # Só tenta montar o device fixo do Ventoy se o destino escolhido
        # for de fato o Ventoy (comportamento padrão) — se o usuário
        # escolheu outro disco na UI, ele já está montado (veio de
        # list_disks(), que só lista o que já tem mountpoint ativo).
        if dest_dir == VENTOY:
            ensure_mounted(VENTOY_DEVICE, VENTOY)
        ensure_mounted(MDSATA_DEVICE, MDSATA)
    except Exception as exc:  # noqa: BLE001
        dialog.append_log(tr("eggs_core.log_error_prefix").format(msg=exc))
        _finish(dialog, False, "", tr("eggs_core.status_mount_fail"))
        return

    if not dest_dir.exists() or not dest_dir.is_dir():
        dialog.append_log(tr("eggs_core.log_invalid_dest").format(dest_dir=dest_dir))
        _finish(dialog, False, "", tr("eggs_core.status_invalid_dest"))
        return

    # Checa PRIMEIRO se já existe uma ISO pronta de uma tentativa anterior
    # (por exemplo, se a etapa de mover pro destino falhou antes, mas o
    # `eggs produce` já tinha terminado com sucesso) — só limpa
    # EGGS_DIRECTORY se não houver nada aproveitável, pra nunca apagar
    # uma ISO de 30+ GB já pronta sem tentar salvá-la primeiro.
    iso_files = _find_produced_iso()
    if iso_files:
        dialog.append_log(tr("eggs_core.log_existing_iso_found").format(parent=iso_files[0].parent))
        resolved_dest = check_space(dialog, dest_dir)
        if resolved_dest is None:
            return
        dest_dir = resolved_dest
        dialog.progress.setRange(0, 100)

        def _on_move_done(ok: bool) -> None:
            _finish(dialog, ok, tr("eggs_core.status_done_ok"), tr("eggs_core.status_op_failed"))

        _start_move_and_backup(dialog, iso_files, dest_dir, _on_move_done)
        return

    dialog.append_log(tr("eggs_core.log_cleaning").format(dir=EGGS_DIRECTORY))
    _safe_remove_eggs_dir()

    resolved_dest = check_space(dialog, dest_dir)
    if resolved_dest is None:
        return
    dest_dir = resolved_dest

    # Nenhuma iso encontrada — gera uma nova via `eggs produce`
    dialog.set_status(tr("eggs_core.status_generating_iso"))
    dialog.append_log("")
    dialog.append_log(tr("eggs_core.log_starting_generate"))
    dialog.append_log("")

    worker = ShellWorker(
        # --prefix precisa do separador manual: o xorriso-command.ts do
        # próprio eggs concatena "prefix + volid" sem underscore entre
        # eles (era isso que gerava "ARCHLINUXarchlinux_amd64..."). O
        # --basename foi removido: no código fonte, o volid é calculado
        # ANTES do override de basename ser aplicado (bug de ordem no
        # fertilization.ts do eggs) — a flag nunca teve efeito nenhum.
        ["eggs", "produce", "--clone", "--nointeractive", "--prefix=ARCHLINUX_"],
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
    worker.progress_changed.connect(dialog.set_progress_percent)

    def on_ok() -> None:
        dialog.append_log(tr("eggs_core.log_iso_generated"))
        dialog.progress.setRange(0, 100)
        new_isos = _find_produced_iso()
        if new_isos:
            def _on_move_done(ok: bool) -> None:
                _finish(dialog, ok, tr("eggs_core.status_done_ok"), tr("eggs_core.status_op_failed"))

            _start_move_and_backup(dialog, new_isos, dest_dir, _on_move_done)
        else:
            _finish(dialog, True, tr("eggs_core.status_iso_generated_not_found"), "")

    def on_fail(msg: str) -> None:
        if getattr(dialog, '_cancelled', False) or getattr(worker, '_cancelled', False):
            dialog.set_current_file("—")
            dialog.progress.setRange(0, 100)
            dialog.progress.setValue(0)
            dialog.set_running(False)
            dialog.btn_close.setEnabled(True)
            return
        dialog.append_log(tr("eggs_core.log_error_prefix").format(msg=msg))
        _finish(dialog, False, "", tr("eggs_core.status_generate_fail"))

    worker.finished_ok.connect(on_ok)
    worker.failed.connect(on_fail)
    worker.start()


def check_eggs(dialog, parent=None, destination: str | None = None) -> None:
    """Verifica se há .iso pendente; move/backup se houver, senão limpa o diretório."""
    require_root()

    dest_dir = Path(destination) if destination else VENTOY

    dialog.set_running(True)
    dialog.progress.setRange(0, 0)
    dialog.set_status(tr("eggs_core.status_checking_devices"))
    dialog.set_current_file("—")
    dialog.append_log(tr("eggs_core.log_header_check"))

    try:
        if dest_dir == VENTOY:
            ensure_mounted(VENTOY_DEVICE, VENTOY)
        ensure_mounted(MDSATA_DEVICE, MDSATA)
    except Exception as exc:  # noqa: BLE001
        dialog.append_log(tr("eggs_core.log_error_prefix").format(msg=exc))
        _finish(dialog, False, "", tr("eggs_core.status_mount_fail"))
        return

    dialog.progress.setRange(0, 100)
    iso_files = _find_produced_iso()

    if iso_files:
        found_dir = iso_files[0].parent
        dialog.append_log(tr("eggs_core.log_iso_found_count").format(count=len(iso_files), dir=found_dir))
        resolved_dest = check_space(dialog, dest_dir)
        if resolved_dest is None:
            return
        dest_dir = resolved_dest

        def _on_move_done(ok: bool) -> None:
            _finish(dialog, ok, tr("eggs_core.status_done_ok"), tr("eggs_core.status_op_failed"))

        _start_move_and_backup(dialog, iso_files, dest_dir, _on_move_done)
        return

    dialog.append_log(tr("eggs_core.log_no_iso_found").format(a=EGGS_DIRECTORY / "mnt", b=EGGS_DIRECTORY, c=FILEPATH))
    dialog.append_log(tr("eggs_core.log_cleaning").format(dir=EGGS_DIRECTORY))
    _safe_remove_eggs_dir()
    _finish(dialog, True, tr("eggs_core.status_dir_cleaned_nothing"), "")


_PACMAN_LOCK = Path("/var/lib/pacman/db.lck")


def _clear_stale_pacman_lock(dialog) -> None:
    """Detecta e remove o lock órfão do pacman (mesma lógica do alias
    `pacrm` do Apollo) — só remove se confirmar que não existe nenhum
    processo pacman/paru/yay REALMENTE rodando. Remover o lock com um
    desses processos genuinamente ativo corrompe o banco de dados."""
    if not _PACMAN_LOCK.exists():
        return

    # pgrep -x "pacman|paru|yay" tem um bug de precedência de regex: o -x
    # ancora só as pontas do padrão INTEIRO (^pacman|paru|yay$), não cada
    # alternativa — "paru" fica sem âncora nenhuma e pode casar com
    # qualquer processo que contenha esse texto em qualquer lugar do
    # nome. Chamadas separadas evitam essa ambiguidade por completo.
    real_process_running = any(
        subprocess.run(
            ["pgrep", "-x", name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
        for name in ("pacman", "paru", "yay")
    )

    if real_process_running:
        dialog.append_log(tr("eggs_core.log_lock_real_process"))
        return

    try:
        _PACMAN_LOCK.unlink()
        dialog.append_log(tr("eggs_core.log_lock_removed"))
    except OSError as exc:
        dialog.append_log(tr("eggs_core.log_lock_remove_fail").format(exc=exc))


def _ensure_pacman_contrib(dialog) -> None:
    """Garante que o pacman-contrib está instalado — é dele que vem o
    checkupdates, usado por check_eggs_update() pra achar atualização
    quando o penguins-eggs vem de repositório normal (não AUR). Sem
    isso instalado, check_eggs_update() volta silenciosamente a só
    checar via paru -Qua, reproduzindo o bug do falso negativo de
    'sem atualização' quando na verdade tem."""
    already_installed = subprocess.run(
        ["pacman", "-Q", "pacman-contrib"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    if already_installed:
        return

    dialog.append_log(tr("eggs_core.log_installing_pacman_contrib"))
    result = subprocess.run(
        ["pacman", "-Sy", "--noconfirm", "--needed", "pacman-contrib"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        dialog.append_log(tr("eggs_core.log_pacman_contrib_installed"))
    else:
        dialog.append_log(tr("eggs_core.log_pacman_contrib_fail").format(err=result.stderr.strip()))


def install_eggs(dialog, parent=None) -> None:
    """Instala o penguins-eggs e o módulo Calamares, se necessário."""
    require_root()

    dialog.set_running(True)
    dialog.progress.setRange(0, 0)
    dialog.set_status(tr("eggs_core.status_checking_install"))
    dialog.set_current_file("—")
    dialog.append_log(tr("eggs_core.log_header_install"))

    _clear_stale_pacman_lock(dialog)
    _ensure_pacman_contrib(dialog)

    eggs_installed = subprocess.run(
        ["pacman", "-Q", "penguins-eggs"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0

    steps: list[list[str]] = []

    if not eggs_installed:
        dialog.append_log(tr("eggs_core.log_eggs_not_found"))
    else:
        dialog.append_log(tr("eggs_core.log_eggs_already_checking"))

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
        dialog.append_log(tr("eggs_core.log_eggs_via_repo"))
        steps.append(["pacman", "-Sy", "--noconfirm", "--needed", "penguins-eggs"])

        # Checagem real ANTES de decidir o texto central — sem isso, o
        # diálogo sempre dizia "Instalando..." mesmo quando não havia
        # nada de fato pra instalar (só verificação). -Sy aqui é rápido
        # (só sincroniza os bancos, não instala nada ainda) e -Qu lista
        # o pacote só se existir versão nova nos repos sincronizados.
        if eggs_installed:
            dialog.set_status(tr("eggs_core.status_syncing_dbs"))
            subprocess.run(["pacman", "-Sy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            qu = subprocess.run(
                ["pacman", "-Qu", "penguins-eggs"],
                capture_output=True, text=True,
            )
            update_available = bool(qu.stdout.strip())
            dialog.set_title(tr("eggs_core.title_installing") if update_available else tr("eggs_core.title_checking_updates"))
            if not update_available:
                dialog.append_log(tr("eggs_core.log_pacman_no_update"))
        else:
            dialog.set_title(tr("eggs_core.title_installing"))
    else:
        dialog.set_title(tr("eggs_core.title_installing"))
        dialog.append_log(tr("eggs_core.log_fallback_fresh_eggs"))
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
        dialog.append_log(tr("eggs_core.log_calamares_not_found"))
    else:
        dialog.append_log(tr("eggs_core.log_calamares_already_checking"))

    # Bug conhecido de empacotamento do penguins-eggs no Arch: o pacote
    # grava a config como "settings.yml", mas o comando "eggs calamares
    # --install" procura "settings.yaml" (com "a") e falha com ENOENT
    # fatal se não achar. Auto-cura: copia .yml -> .yaml se a versão
    # certa ainda não existir. Não sobrescreve se já existir (pode ter
    # sido customizado); só cria a cópia que falta.
    _calamares_cfg_dir = Path("/etc/penguins-eggs.d/distros/archlinux/calamares")
    _settings_yml = _calamares_cfg_dir / "settings.yml"
    _settings_yaml = _calamares_cfg_dir / "settings.yaml"
    if _settings_yml.exists() and not _settings_yaml.exists():
        try:
            shutil.copy2(_settings_yml, _settings_yaml)
            dialog.append_log(tr("eggs_core.log_settings_autofix"))
        except OSError as exc:
            dialog.append_log(tr("eggs_core.log_settings_autofix_fail").format(exc=exc))

    steps.append(["eggs", "calamares", "--install"])

    # Detecta se o pacman realmente não tinha nada pra atualizar (marcador
    # "is up to date -- skipping" ou "there is nothing to do") — usado só
    # pra ajustar a mensagem final, não afeta o resultado (sucesso é
    # sucesso de qualquer jeito).
    nothing_to_update = {"flag": False}
    _NOTHING_TO_UPDATE_MARKERS = ("is up to date -- skipping", "there is nothing to do")

    def run_next(index: int = 0) -> None:
        if index >= len(steps):
            if eggs_installed and nothing_to_update["flag"]:
                dialog.append_log(tr("eggs_core.log_verification_done"))
                _finish(dialog, True, tr("eggs_core.status_no_update"), "")
            else:
                action = tr("eggs_core.word_update") if eggs_installed else tr("eggs_core.word_install")
                dialog.append_log(tr("eggs_core.log_action_done").format(action=action.lower()))
                _finish(dialog, True, tr("eggs_core.status_action_done_ok").format(action=action), "")
            return

        cmd = steps[index]

        # Ruído cosmético conhecido: o `eggs calamares --install` tenta
        # `pacman -S calamares` mesmo com `calamares-eggs` já instalado
        # (que supre a mesma necessidade), falha, e segue em frente
        # normalmente — não é uma falha real do comando. Suprimimos só
        # essas duas linhas específicas, só nesse comando.
        suppress = None
        if cmd == ["eggs", "calamares", "--install"]:
            suppress = ["pacman -S calamares --noconfirm", "error: target not found: calamares"]

        worker = ShellWorker(cmd, title="Instalando...", suppress_patterns=suppress, parent=dialog)

        register = getattr(dialog, "register_worker", None)
        if callable(register):
            dialog.register_worker(worker)
        else:
            dialog._worker = worker

        def _watch_for_nothing_to_update(line: str) -> None:
            if any(marker in line for marker in _NOTHING_TO_UPDATE_MARKERS):
                nothing_to_update["flag"] = True

        worker.log_line.connect(_watch_for_nothing_to_update)
        worker.log_line.connect(dialog.append_log)
        worker.file_changed.connect(dialog.set_current_file)
        worker.progress_changed.connect(dialog.set_progress_percent)

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
            dialog.append_log(tr("eggs_core.log_error_prefix").format(msg=msg))
            _finish(dialog, False, "", tr("eggs_core.status_install_fail"))

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
