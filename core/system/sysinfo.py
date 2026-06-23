from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SystemInfo:
    os_name: str
    kernel: str
    uptime: str
    packages: str
    cpu: str
    memory: str
    hostname: str
    user: str


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return ""


def _get_os_name() -> str:
    os_release = Path("/etc/os-release")
    if os_release.exists():
        text = os_release.read_text()
        match = re.search(r'^PRETTY_NAME="(.+)"$', text, re.MULTILINE)
        if match:
            return f"{match.group(1)} {platform.machine()}"
    return f"{platform.system()} {platform.machine()}"


def _get_uptime() -> str:
    try:
        with open("/proc/uptime") as f:
            seconds = float(f.read().split()[0])
    except Exception:
        return "unknown"

    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m" if mins or not parts else "0m")
    return " ".join(parts)


def _get_package_count() -> str:
    pacman_count = _run(["pacman", "-Qq"])
    pacman_n = len(pacman_count.splitlines()) if pacman_count else 0

    flatpak_count = _run(["flatpak", "list", "--app"])
    flatpak_n = len(flatpak_count.splitlines()) if flatpak_count else 0

    parts = []
    if pacman_n:
        parts.append(f"{pacman_n} (pacman)")
    if flatpak_n:
        parts.append(f"{flatpak_n} (flatpak)")
    return ", ".join(parts) if parts else "unknown"


def _get_cpu() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            text = f.read()
        match = re.search(r"^model name\s*:\s*(.+)$", text, re.MULTILINE)
        cores = len(re.findall(r"^processor\s*:", text, re.MULTILINE))
        if match:
            name = match.group(1).strip()
            name = re.sub(r"\s*@.*", "", name)  # remove "@ X.XGHz" verbose
            return f"{name} ({cores})"
    except Exception:
        pass
    return platform.processor() or "unknown"


def _get_memory() -> str:
    try:
        with open("/proc/meminfo") as f:
            text = f.read()
        total_match = re.search(r"MemTotal:\s*(\d+)\s*kB", text)
        avail_match = re.search(r"MemAvailable:\s*(\d+)\s*kB", text)
        if total_match and avail_match:
            total_kb = int(total_match.group(1))
            avail_kb = int(avail_match.group(1))
            used_kb = total_kb - avail_kb
            used_mib = used_kb // 1024
            total_mib = total_kb // 1024
            return f"{used_mib}MiB / {total_mib}MiB"
    except Exception:
        pass
    return "unknown"


def get_system_info() -> SystemInfo:
    return SystemInfo(
        os_name=_get_os_name(),
        kernel=platform.release(),
        uptime=_get_uptime(),
        packages=_get_package_count(),
        cpu=_get_cpu(),
        memory=_get_memory(),
        hostname=platform.node(),
        user=Path.home().name,
    )
