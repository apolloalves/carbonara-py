from __future__ import annotations

import os
import subprocess
from pathlib import Path

from core.snapshots.restore import (
    RAID_MEMBERS,
    RAID_DEVICE,
    PART_ROOT,
    PART_BOOT,
    PART_HOME,
    UUID_ROOT,
    UUID_BOOT,
    UUID_HOME,
    MOUNT_TARGET,
)

# Discos externos conhecidos — mesmos UUIDs já usados em restore.py
# (BACK_EMERGENCY == FALLBACK_UUID_BACKUP) e no /etc/fstab real do
# sistema instalado. Cada um é tentado de forma independente — se um
# não existir nesse ambiente (ex: pendrive desconectado), os outros
# continuam sendo tentados normalmente.
#
# VENTOY é marcado como não-essencial: é o próprio disco de onde a
# live deu boot, então já está em uso por baixo dos panos (visto ao
# vivo: /run/archiso/bootmnt é /dev/mapper/ventoy) — falhar ao montar
# de novo em /mnt/VENTOY é o resultado ESPERADO, não um problema. Sem
# essa marcação, o banner "ainda não montado" nunca desaparecia,
# mesmo com RAID+BACK_EMERGENCY+MDSATA já montados de verdade.
KNOWN_EXTERNAL_DISKS = [
    {"label": "BACK_EMERGENCY", "uuid": "1499c321-423d-40cf-a8a5-269e2e25c8d4", "mountpoint": "/mnt/BACK_EMERGENCY", "essential": True},
    {"label": "MDSATA", "uuid": "82770cba-e03a-4dc7-817f-26a408836239", "mountpoint": "/mnt/MDSATA", "essential": True},
    {"label": "VENTOY", "uuid": "E626-528A", "mountpoint": "/mnt/VENTOY", "essential": False},
]


def is_live_environment() -> bool:
    """Detecta um ambiente live boot (ex: a própria ISO gerada pelo
    Eggs) — nesses casos não existe /etc/fstab real do sistema
    instalado, então nada vem montado por padrão. O Carbonara não
    quebra nesse cenário (só fica sem dado pra mostrar), então isso
    serve pra decidir quando oferecer o botão de montagem, não pra
    bloquear nada."""
    if Path("/run/archiso").exists():
        return True
    try:
        result = subprocess.run(
            ["findmnt", "-no", "FSTYPE", "/"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() in ("airootfs", "overlay", "squashfs")
    except Exception:
        return False


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def mount_system_disks() -> dict[str, str]:
    """Tenta montar o RAID0 (só leitura, é inspeção — não é restore) e
    os discos externos conhecidos, um a um, tolerando falha em
    qualquer item individual sem abortar os demais. Retorna um
    relatório {item: resultado} pra exibir na UI."""
    results: dict[str, str] = {}

    # ── RAID0 + partições do sistema (só leitura) ────────────────────
    _run(["mdadm", "--assemble", RAID_DEVICE, *RAID_MEMBERS])
    if not Path(RAID_DEVICE).exists():
        _run(["mdadm", "--assemble", "--scan"])

    if Path(RAID_DEVICE).exists():
        test = _run(["mdadm", "--detail", "--test", RAID_DEVICE])
        if test.returncode == 0:
            results["RAID0"] = "montado e íntegro"
            Path(MOUNT_TARGET).mkdir(parents=True, exist_ok=True)
            for name, uuid, sub in (
                ("ROOT", UUID_ROOT, ""),
                ("BOOT", UUID_BOOT, "/boot"),
                ("HOME", UUID_HOME, "/home"),
            ):
                target = f"{MOUNT_TARGET}{sub}"
                Path(target).mkdir(parents=True, exist_ok=True)
                r = _run(["mount", "-o", "ro", f"UUID={uuid}", target])
                if r.returncode == 0:
                    results[name] = f"montado (só leitura) em {target}"
                else:
                    err = (r.stderr or "").strip()[:80]
                    results[name] = f"falhou: {err}" if err else "falhou"
        else:
            results["RAID0"] = "encontrado mas não íntegro — não montado (evita risco)"
    else:
        results["RAID0"] = "não encontrado neste ambiente"

    # ── Discos externos conhecidos ────────────────────────────────────
    for disk in KNOWN_EXTERNAL_DISKS:
        Path(disk["mountpoint"]).mkdir(parents=True, exist_ok=True)
        r = _run(["mount", f"UUID={disk['uuid']}", disk["mountpoint"]])
        if r.returncode == 0:
            results[disk["label"]] = f"montado em {disk['mountpoint']}"
        elif not disk["essential"]:
            results[disk["label"]] = "não montado (esperado — é o próprio disco de boot da live)"
        else:
            results[disk["label"]] = "não encontrado/não pôde montar"

    return results


def essential_disks_mounted() -> bool:
    """Confere se os discos que REALMENTE importam (RAID + externos
    marcados essential=True) já estão montados de verdade — ignora o
    VENTOY de propósito, já que ele nunca monta na live (é o próprio
    disco de boot) e não deveria contar como 'faltando montar'. Usado
    pra decidir se o banner de aviso ainda faz sentido aparecer."""
    if not os.path.ismount(MOUNT_TARGET):
        return False
    for disk in KNOWN_EXTERNAL_DISKS:
        if disk["essential"] and not os.path.ismount(disk["mountpoint"]):
            return False
    return True
