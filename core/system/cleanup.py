from __future__ import annotations

import glob
import re
import shutil
import subprocess
from pathlib import Path

# Categorias do Cleanup do Doctor Arch. Corrigidas em relação ao
# ArchDeepClean.sh/RubbishBin.sh originais:
#   - removidas as referências a apt/dpkg (resíduo de template Debian,
#     não existe em Arch)
#   - `rm -rf ~/.config/B` (linha truncada) removida — não fazia nada
#   - lixeira usa só `trash-empty`, sem o `rm -rf .../Trash/*i` com typo
#   - journal usa `journalctl --vacuum-time` em vez de `rm -rf /var/log/*`
#     (evita apagar arquivos de log que serviços ativos têm abertos)
CATEGORIES = ["pacman_cache", "orphans", "trash", "journal", "tmp_cache"]


def clean_pacman_cache() -> str:
    subprocess.run(["paccache", "-r", "-k1"], capture_output=True, timeout=60)
    subprocess.run(
        ["find", "/var/cache/pacman/pkg/", "-type", "f", "-name", "*.part"],
        capture_output=True, timeout=30,
    )
    return "Cache do pacman reduzido (mantendo 1 versão por pacote)"


def clean_orphans() -> str:
    result = subprocess.run(["pacman", "-Qtdq"], capture_output=True, text=True, timeout=15)
    orphans = [l for l in result.stdout.splitlines() if l.strip()]
    if not orphans:
        return "Nenhum pacote órfão encontrado"
    subprocess.run(["pacman", "-Rns", "--noconfirm", *orphans], capture_output=True, timeout=120)
    return f"{len(orphans)} pacote(s) órfão(s) removido(s)"


def clean_trash() -> str:
    subprocess.run(["trash-empty", "--all", "-f"], capture_output=True, timeout=30)
    for p in glob.glob("/home/*/.local/share/recently-used.xbel"):
        Path(p).unlink(missing_ok=True)
    return "Lixeira e lista de recentes limpas"


def clean_journal() -> str:
    subprocess.run(["journalctl", "--vacuum-time=7d"], capture_output=True, timeout=30)
    return "Journal reduzido para os últimos 7 dias"


def clean_tmp_cache() -> str:
    removed = 0
    for pattern in ("/home/*/.cache/thumbnails/*", "/home/*/.cache/icon*"):
        for p in glob.glob(pattern):
            path = Path(p)
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass
    return f"Cache de thumbnails/ícones limpo ({removed} item(ns))"


def _du_bytes(path: Path, timeout: int = 10) -> int:
    if not path.exists():
        return 0
    try:
        out = subprocess.run(["du", "-sb", str(path)], capture_output=True, text=True, timeout=timeout)
        return int(out.stdout.split()[0]) if out.stdout else 0
    except Exception:
        return 0


def estimate_pacman_cache() -> int:
    out = subprocess.run(["paccache", "-d", "-k1"], capture_output=True, text=True, timeout=30)
    total = 0
    for line in out.stdout.splitlines():
        path = Path(line.strip())
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def estimate_orphans() -> int:
    result = subprocess.run(["pacman", "-Qtdq"], capture_output=True, text=True, timeout=15)
    orphans = [l for l in result.stdout.splitlines() if l.strip()]
    total = 0
    for pkg in orphans:
        info = subprocess.run(["pacman", "-Qi", pkg], capture_output=True, text=True, timeout=10)
        for line in info.stdout.splitlines():
            if line.startswith("Installed Size"):
                size_str = line.split(":", 1)[1].strip()
                total += _parse_pacman_size(size_str)
    return total


def _parse_pacman_size(size_str: str) -> int:
    parts = size_str.split()
    if len(parts) != 2:
        return 0
    try:
        value = float(parts[0])
    except ValueError:
        return 0
    unit = parts[1].upper()
    multipliers = {"B": 1, "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3}
    return int(value * multipliers.get(unit, 1))


def estimate_trash() -> int:
    return _du_bytes(Path.home() / ".local/share/Trash", timeout=10)


def estimate_journal_reclaimable() -> int:
    """Estimativa aproximada: tamanho total atual do journal — o real
    reclamável (>7 dias) só se sabe rodando o vacuum de verdade, mas
    dá uma ideia de teto."""
    out = subprocess.run(["journalctl", "--disk-usage"], capture_output=True, text=True, timeout=15)
    match = re.search(r"([\d.]+)([KMGT]?)B", out.stdout)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2)
    multipliers = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}
    return int(value * multipliers.get(unit, 1))


def estimate_tmp_cache() -> int:
    total = 0
    for pattern in ("*/.cache/thumbnails", "*/.cache/icon*"):
        try:
            for p in Path("/home").glob(pattern):
                total += _du_bytes(p, timeout=5)
        except OSError:
            pass
    return total


ESTIMATORS = {
    "pacman_cache": estimate_pacman_cache,
    "orphans": estimate_orphans,
    "trash": estimate_trash,
    "journal": estimate_journal_reclaimable,
    "tmp_cache": estimate_tmp_cache,
}


def estimate_cleanup_size() -> tuple[dict[str, int], int]:
    """Tamanho estimado por categoria, em bytes. Somente leitura, sem
    privilégio (algumas leituras de /var/cache podem retornar 0 se o
    usuário não tiver permissão — não é erro, só fica sem estimar essa
    categoria)."""
    per_category: dict[str, int] = {}
    for cat, fn in ESTIMATORS.items():
        try:
            per_category[cat] = fn()
        except Exception:
            per_category[cat] = 0
    return per_category, sum(per_category.values())


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


RUNNERS = {
    "pacman_cache": clean_pacman_cache,
    "orphans": clean_orphans,
    "trash": clean_trash,
    "journal": clean_journal,
    "tmp_cache": clean_tmp_cache,
}


def run_cleanup(categories: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for cat in categories:
        runner = RUNNERS.get(cat)
        if runner is None:
            continue
        try:
            results[cat] = runner()
        except Exception as exc:
            results[cat] = f"Erro: {exc}"
    return results
