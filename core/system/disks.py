from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskInfo:
    name: str
    model: str
    path: str
    fstype: str
    mountpoint: str
    size: str
    used: str
    avail: str
    use_pct: str


@dataclass(frozen=True)
class RaidInfo:
    device: str
    level: str
    state: str
    members: list[str]
    array_size: str


def parse_size_to_gb(size_str: str) -> float:
    """Converte strings human-readable do lsblk (ex: '65.7G', '512M',
    '1.2T') pra GB numérico — usado pra ordenar/filtrar por espaço livre."""
    if not size_str:
        return 0.0
    size_str = size_str.strip()
    try:
        unit = size_str[-1].upper()
        value = float(size_str[:-1])
    except (ValueError, IndexError):
        return 0.0
    multipliers = {"K": 1 / (1024 ** 2), "M": 1 / 1024, "G": 1, "T": 1024}
    return value * multipliers.get(unit, 1)


IGNORED_MOUNT_PREFIXES = ("/run", "/boot", "/sys", "/proc", "/dev")
IGNORED_FSTYPES = {"swap", "tmpfs", "devtmpfs", "squashfs", "overlay", "iso9660"}


def list_relevant_disks(disks: list[DiskInfo] | None = None) -> list[DiskInfo]:
    """Filtra discos irrelevantes como destino de backup/ISO (/run, /boot,
    swap, tmpfs, etc.) e ordena por espaço livre disponível, maior
    primeiro — mesmo critério usado pelo seletor de destino do Timeshift
    e pelo combo de destino da ISO no Eggs."""
    base = disks if disks is not None else list_disks()
    filtered = [
        d for d in base
        if d.mountpoint
        and not d.mountpoint.startswith(IGNORED_MOUNT_PREFIXES)
        and d.fstype not in IGNORED_FSTYPES
    ]
    filtered.sort(key=lambda d: parse_size_to_gb(d.avail), reverse=True)
    return filtered


def run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout
    except Exception:
        return ""


def list_disks() -> list[DiskInfo]:
    """Equivalente a 'lsblkd' do .bashrc — lsblk com colunas customizadas.

    lsblk pode listar a mesma partição mais de uma vez quando ela aparece
    em hierarquias diferentes (ex: membro de RAID + ponto de montagem).
    Deduplicamos por 'path' para garantir que cada volume apareça uma vez.
    """
    out = run([
        "lsblk", "--output=NAME,MODEL,PATH,FSSIZE,FSUSED,FSAVAIL,FSUSE%,FSTYPE,MOUNTPOINTS",
        "--json",
    ])
    disks: list[DiskInfo] = []
    seen_paths: set[str] = set()
    if not out:
        return disks

    try:
        data = json.loads(out)
    except Exception:
        return disks

    def walk(devices):
        for dev in devices:
            mounts = dev.get("mountpoints") or []
            mount = mounts[0] if mounts and mounts[0] else ""
            path = dev.get("path", "")
            if dev.get("fstype") and mount and path not in seen_paths:
                seen_paths.add(path)
                disks.append(DiskInfo(
                    name=dev.get("name", ""),
                    model=dev.get("model") or "",
                    path=path,
                    fstype=dev.get("fstype") or "",
                    mountpoint=mount,
                    size=dev.get("fssize") or "",
                    used=dev.get("fsused") or "",
                    avail=dev.get("fsavail") or "",
                    use_pct=dev.get("fsuse%") or "",
                ))
            if dev.get("children"):
                walk(dev["children"])

    walk(data.get("blockdevices", []))
    return disks


def get_raid_info() -> RaidInfo | None:
    """Lê /proc/mdstat para detectar arrays RAID ativos.

    Formato típico do /proc/mdstat:
        md127 : active raid0 sda2[0] sdb2[1]
              234207232 blocks super 1.2 512k chunks
              [state info opcional aqui, ex: [UU] para mirror]

    O estado de degradação é indicado por colchetes como [_U] ou [U_]
    na linha seguinte ao cabeçalho, não pela palavra 'active' em si
    (que sempre aparece em arrays ativos, saudáveis ou não).
    """
    mdstat = Path("/proc/mdstat")
    if not mdstat.exists():
        return None

    text = mdstat.read_text()
    match = re.search(r"^(md\d+)\s*:\s*active\s+(\w+)\s+(.+)$", text, re.MULTILINE)
    if not match:
        return None

    device, level, rest = match.groups()
    members = re.findall(r"(\w+)\[\d+\]", rest)

    size_match = re.search(r"(\d+) blocks", text)
    array_size = ""
    if size_match:
        blocks = int(size_match.group(1))
        gb = blocks / (1024 ** 2)
        array_size = f"{gb:.1f} GB"

    # Procura indicador de saúde [UU], [U_], [_U] etc. nas linhas do array
    # RAID0 não tem redundância e por isso não exibe esse indicador —
    # nesse caso, "active" já significa "clean" (não há estado degradado
    # possível para RAID0: ou o array está montado, ou um disco falhou
    # e o array inteiro desaparece do mdstat).
    health_match = re.search(r"\[([U_]+)\]", text)
    if level == "raid0":
        state = "clean"
    elif health_match:
        state = "clean" if "_" not in health_match.group(1) else "degraded"
    else:
        state = "clean"

    return RaidInfo(
        device=f"/dev/{device}",
        level=level,
        state=state,
        members=[f"/dev/{m}" for m in members],
        array_size=array_size,
    )


def get_disk_temps() -> dict[str, str]:
    """Equivalente a 'temp' — hddtemp em todos os discos sd*."""
    temps: dict[str, str] = {}
    sd_devices = sorted(Path("/dev").glob("sd[a-z]"))
    for dev in sd_devices:
        out = run(["sudo", "-n", "hddtemp", str(dev)])
        if out.strip():
            match = re.search(r":\s*(\d+)°?C", out)
            if match:
                temps[str(dev)] = f"{match.group(1)}°C"
            else:
                temps[str(dev)] = out.strip()
    return temps


def get_large_volumes(threshold_pct: int = 40) -> list[DiskInfo]:
    """Equivalente a 'vol' — volumes com uso acima do threshold."""
    disks = list_disks()
    result = []
    for d in disks:
        try:
            pct = int(d.use_pct.rstrip("%")) if d.use_pct else 0
        except ValueError:
            pct = 0
        if pct > threshold_pct:
            result.append(d)
    return result


def find_large_files(path: str = "/", min_size_mb: int = 500) -> list[tuple[str, str]]:
    """Equivalente a 'scan' — arquivos grandes acima de min_size_mb."""
    out = run([
        "sudo", "-n", "find", path,
        "(", "-path", "/proc", "-o", "-path", "/sys", "-o", "-path", "/run", ")",
        "-prune", "-o",
        "-type", "f", "-size", f"+{min_size_mb}M", "-printf", "%s\t%p\n",
    ])
    results: list[tuple[str, str]] = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        size_str, path_str = line.split("\t", 1)
        try:
            size_bytes = int(size_str)
            gb = size_bytes / (1024 ** 3)
            size_fmt = f"{gb:.1f} GB" if gb >= 1 else f"{size_bytes / (1024**2):.0f} MB"
        except ValueError:
            size_fmt = size_str
        results.append((size_fmt, path_str))
    results.sort(key=lambda x: x[1])
    return results
