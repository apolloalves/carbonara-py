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


def run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout
    except Exception:
        return ""


def list_disks() -> list[DiskInfo]:
    """Equivalente a 'lsblkd' do .bashrc — lsblk com colunas customizadas."""
    out = run([
        "lsblk", "--output=NAME,MODEL,PATH,FSSIZE,FSUSED,FSAVAIL,FSUSE%,FSTYPE,MOUNTPOINTS",
        "--json",
    ])
    disks: list[DiskInfo] = []
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
            if dev.get("fstype") and mount:
                disks.append(DiskInfo(
                    name=dev.get("name", ""),
                    model=dev.get("model") or "",
                    path=dev.get("path", ""),
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
    """Lê /proc/mdstat para detectar arrays RAID ativos."""
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

    state = "clean" if "active" in rest else "degraded"

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
