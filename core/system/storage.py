from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


SNAPSHOT_FOLDER_NAME = "CarbonaraSnapshots"


@dataclass(frozen=True)
class StorageDestination:
    label: str
    mountpoint: str
    device: str
    fs_type: str
    total_bytes: int
    free_bytes: int
    used_bytes: int
    backup_root: str

    @property
    def free_gb(self) -> float:
        return self.free_bytes / (1024 ** 3)

    @property
    def total_gb(self) -> float:
        return self.total_bytes / (1024 ** 3)

    @property
    def used_gb(self) -> float:
        return self.used_bytes / (1024 ** 3)


def _human_label_from_mountpoint(mountpoint: str, device: str) -> str:
    base = Path(mountpoint).name.strip()
    if base:
        return base.upper()

    device_name = Path(device).name.strip()
    return device_name.upper() if device_name else mountpoint


def _read_proc_mounts() -> list[tuple[str, str, str]]:
    mounts: list[tuple[str, str, str]] = []

    with open("/proc/mounts", "r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 3:
                continue
            device, mountpoint, fs_type = parts[0], parts[1], parts[2]
            mounts.append((device, mountpoint, fs_type))

    return mounts


def _is_candidate_mount(device: str, mountpoint: str, fs_type: str) -> bool:
    ignored_fs = {
        "proc",
        "sysfs",
        "tmpfs",
        "devtmpfs",
        "devpts",
        "securityfs",
        "cgroup",
        "cgroup2",
        "pstore",
        "autofs",
        "mqueue",
        "hugetlbfs",
        "rpc_pipefs",
        "overlay",
        "squashfs",
        "nsfs",
        "tracefs",
        "debugfs",
        "configfs",
        "fusectl",
        "binfmt_misc",
        "fuse.portal",
    }

    if fs_type in ignored_fs:
        return False

    if mountpoint == "/":
        return False

    if mountpoint in {"/boot", "/boot/efi", "/dev", "/run", "/sys", "/proc"}:
        return False

    if mountpoint.startswith("/proc/"):
        return False

    if mountpoint.startswith("/sys/"):
        return False

    if mountpoint.startswith("/dev/"):
        return False

    if mountpoint.startswith("/run/"):
        return False

    # Apenas destinos úteis para backup
    if not (
        mountpoint.startswith("/mnt/")
        or mountpoint.startswith("/media/")
        or mountpoint.startswith("/run/media/")
    ):
        return False

    # Evita mounts genéricos sem device real
    if not device or device == "none":
        return False

    return True


def get_backup_root(mountpoint: str) -> str:
    return str(Path(mountpoint) / SNAPSHOT_FOLDER_NAME)


def get_destination_usage(mountpoint: str) -> tuple[int, int, int]:
    stat = os.statvfs(mountpoint)
    total = stat.f_frsize * stat.f_blocks
    free = stat.f_frsize * stat.f_bavail
    used = total - free
    return total, free, used


def list_backup_destinations() -> List[StorageDestination]:
    destinations: List[StorageDestination] = []

    for device, mountpoint, fs_type in _read_proc_mounts():
        if not _is_candidate_mount(device, mountpoint, fs_type):
            continue

        try:
            total, free, used = get_destination_usage(mountpoint)
        except OSError:
            continue

        label = _human_label_from_mountpoint(mountpoint, device)
        backup_root = get_backup_root(mountpoint)

        destinations.append(
            StorageDestination(
                label=label,
                mountpoint=mountpoint,
                device=device,
                fs_type=fs_type,
                total_bytes=total,
                free_bytes=free,
                used_bytes=used,
                backup_root=backup_root,
            )
        )

    destinations.sort(key=lambda d: d.free_bytes, reverse=True)
    return destinations


def ensure_backup_root(mountpoint: str, scope: str = "both") -> Path:
    """
    Cria a árvore CarbonaraSnapshots apenas quando for realmente gravar backup.
    Não use isso na listagem da UI.

    `scope` decide QUAIS subpastas (ROOT/HOME) são criadas — antes criava
    as duas sempre, deixando uma pasta vazia e órfã pro kind que nem foi
    selecionado.
    """
    root = Path(get_backup_root(mountpoint))
    root.mkdir(parents=True, exist_ok=True)
    if scope in ("root", "both"):
        (root / "ROOT").mkdir(parents=True, exist_ok=True)
    if scope in ("home", "both"):
        (root / "HOME").mkdir(parents=True, exist_ok=True)
    return root


def format_gb(value: float) -> str:
    return f"{value:.1f} GB"


def format_destination_line(dest: StorageDestination) -> str:
    return (
        f"{dest.label}  •  {format_gb(dest.free_gb)} livre  •  "
        f"{dest.mountpoint}  •  {dest.fs_type}"
    )
