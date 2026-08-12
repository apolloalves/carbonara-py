from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CLONEZILLA_ROOT = Path("/mnt/MDSATA/CLONEZILLA")

# Arquivo que só existe dentro de uma pasta de imagem Clonezilla "crua" —
# usado pra distinguir uma pasta de imagem válida de qualquer outra pasta
# que porventura exista dentro de <ano>/<mês>/.
_CLONEZILLA_MARKER_FILE = "clonezilla-img"

# Arquivos .tar.zst menores que isso são tratados como incompletos/inválidos
# (sobra de uma compressão cancelada ou que falhou antes de escrever
# qualquer coisa útil) — não contam como "já comprimido".
_MIN_VALID_ARCHIVE_BYTES = 4096


def require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("Este módulo precisa ser executado como root.")


@dataclass
class ClonezillaEntry:
    name: str
    month_dir: Path
    raw_path: Path | None
    archive_path: Path | None
    raw_size_bytes: int | None
    archive_size_bytes: int | None
    modified_at: datetime

    @property
    def status(self) -> str:
        """'raw' (só a pasta crua), 'compressed' (só o .tar.zst) ou 'both'."""
        if self.raw_path and self.archive_path:
            return "both"
        if self.archive_path:
            return "compressed"
        return "raw"


def _dir_size_bytes(path: Path) -> int | None:
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = Path(dirpath) / f
                try:
                    total += fp.stat().st_size
                except OSError:
                    continue
    except OSError:
        return None
    return total


def scan_clonezilla_backups(root: Path = CLONEZILLA_ROOT) -> list[ClonezillaEntry]:
    """Varre <root>/<ano>/<mês>/ procurando pastas cruas do Clonezilla
    (marcadas pela presença de 'clonezilla-img' dentro) e/ou arquivos
    .tar.zst já comprimidos, agrupando pelo mesmo nome base."""
    entries: dict[str, ClonezillaEntry] = {}

    if not root.is_dir():
        return []

    for year_dir in sorted(root.iterdir(), reverse=True):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.iterdir(), reverse=True):
            if not month_dir.is_dir():
                continue

            for item in month_dir.iterdir():
                if item.is_dir() and (item / _CLONEZILLA_MARKER_FILE).exists():
                    key = f"{month_dir}/{item.name}"
                    entry = entries.get(key) or ClonezillaEntry(
                        name=item.name, month_dir=month_dir,
                        raw_path=None, archive_path=None,
                        raw_size_bytes=None, archive_size_bytes=None,
                        modified_at=datetime.fromtimestamp(item.stat().st_mtime),
                    )
                    entry.raw_path = item
                    entry.raw_size_bytes = _dir_size_bytes(item)
                    entries[key] = entry

                elif item.is_file() and item.name.endswith(".tar.zst"):
                    try:
                        size = item.stat().st_size
                    except OSError:
                        continue
                    if size < _MIN_VALID_ARCHIVE_BYTES:
                        # Sobra de uma compressão cancelada/falhada — ignora,
                        # pra pasta original continuar aparecendo em Pendentes.
                        continue

                    name = item.name[: -len(".tar.zst")]
                    key = f"{month_dir}/{name}"
                    entry = entries.get(key) or ClonezillaEntry(
                        name=name, month_dir=month_dir,
                        raw_path=None, archive_path=None,
                        raw_size_bytes=None, archive_size_bytes=None,
                        modified_at=datetime.fromtimestamp(item.stat().st_mtime),
                    )
                    entry.archive_path = item
                    entry.archive_size_bytes = size
                    entries[key] = entry

    return sorted(entries.values(), key=lambda e: e.modified_at, reverse=True)


def compress_backup(dialog, name: str, month_dir: str) -> None:
    """Comprime <month_dir>/<name>/ em <month_dir>/<name>.tar.zst
    (tar + zstd, mesma ideia da função `compress()` do .bashrc), com
    progresso real via `pv`. Precisa rodar como root — chamado a partir
    do carbonara-helper via pkexec, igual ao create_backup()."""
    require_root()

    from core.workers.clonezilla_worker import ClonezillaCompressWorker

    month_path = Path(month_dir)
    raw_path = month_path / name
    archive_path = month_path / f"{name}.tar.zst"

    if not raw_path.is_dir():
        dialog.set_status(f"Pasta não encontrada: {raw_path}")
        dialog.append_log(f"ERRO: pasta não encontrada: {raw_path}")
        dialog.set_running(False)
        return

    dialog.set_running(True)
    dialog.progress.setRange(0, 100)
    dialog.progress.setValue(0)
    dialog.set_status(f"Preparando compressão de {name}...")
    dialog.set_current_file(str(raw_path))
    dialog.append_log(f"=== COMPRESS {name} ===")

    worker = ClonezillaCompressWorker(raw_path=raw_path, archive_path=archive_path, parent=dialog)

    register = getattr(dialog, "register_worker", None)
    if callable(register):
        dialog.register_worker(worker)
    else:
        dialog._worker = worker

    worker.progress_changed.connect(dialog.progress.setValue)
    worker.status_changed.connect(dialog.set_status)
    worker.log_line.connect(dialog.append_log)
    if hasattr(dialog, "set_progress_detail"):
        worker.detail_changed.connect(dialog.set_progress_detail)
    if hasattr(dialog, "build_tree"):
        worker.tree_ready.connect(dialog.build_tree)
    if hasattr(dialog, "mark_file_done"):
        worker.file_done.connect(dialog.mark_file_done)
        worker.file_done.connect(dialog.set_current_file)

    def _on_done() -> None:
        dialog.set_status(f"Compressão concluída: {archive_path.name}")
        dialog.set_current_file("—")
        dialog.progress.setValue(100)
        dialog.set_running(False)
        if hasattr(dialog, "btn_close"):
            dialog.btn_close.setEnabled(True)

    def _on_failed(msg: str) -> None:
        dialog.append_log(f"ERRO: {msg}")
        dialog.set_status("Compressão falhou.")
        dialog.set_running(False)
        if hasattr(dialog, "btn_close"):
            dialog.btn_close.setEnabled(True)

    worker.finished_ok.connect(_on_done)
    worker.failed.connect(_on_failed)

    worker.start()
