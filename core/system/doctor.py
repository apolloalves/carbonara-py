from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Level = Literal["critical", "warning", "ok"]

# Timers que já resolvem manutenção automática — o Doctor Arch só verifica
# se continuam vivos e rodando com sucesso, não reimplementa a lógica deles.
CRITICAL_TIMERS = [
    "paccache.timer",
    "reflector.timer",
    "archlinux-keyring-wkd-sync.timer",
]

# Diretórios de log que pacotes esperam existir (origem: FixArch.sh) —
# ausência costuma aparecer como "missing file" em pacman -Qk sem ser
# corrupção real.
EXPECTED_LOG_DIRS = [
    "/var/log/httpd",
    "/var/log/glusterfs",
    "/var/log/libvirt/ch",
    "/var/log/libvirt/lxc",
    "/var/log/libvirt/qemu",
    "/var/log/swtpm/libvirt",
    "/var/log/swtpm/libvirt/qemu",
    "/var/log/journal",
    "/var/log/old",
]

# Pacotes AUR observados por atualização — hoje só o driver legado do
# GTX 780 Ti, mas a lista é pensada pra crescer sem mudar o código.
AUR_WATCHLIST = [
    {
        "package": "nvidia-470xx-dkms",
        "log_glob": "/home/*/Timers/dkms/nvidia-*.log",
    },
]


@dataclass(frozen=True)
class Finding:
    id: str
    title: str
    detail: str
    level: Level
    category: str
    count: int = 0
    fixable: bool = False


@dataclass(frozen=True)
class DoctorReport:
    findings: list[Finding] = field(default_factory=list)
    score: int = 100

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.level == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.level == "warning")


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception:
        return ""


# ────────────────────────────────────────────────────────────── diagnósticos --

def check_failed_services() -> Finding:
    out = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    lines = [l for l in out.splitlines() if l.strip()]
    n = len(lines)
    if n == 0:
        return Finding("failed_services", "Serviços", "Nenhum serviço com falha",
                        "ok", "sistema")
    first_unit = lines[0].split()[0] if lines[0].split() else "?"
    return Finding("failed_services", "Serviços com falha",
                    f"{n} serviço(s) — ex: {first_unit}", "critical", "sistema", count=n)


def check_pacnew_pacsave() -> Finding:
    out = _run(["find", "/etc", "-type", "f", "(", "-name", "*.pacnew", "-o", "-name", "*.pacsave", ")"])
    lines = [l for l in out.splitlines() if l.strip()]
    n = len(lines)
    if n == 0:
        return Finding("pacnew", "Pacnew / pacsave", "Nenhuma config pendente de merge",
                        "ok", "diagnostico")
    return Finding("pacnew", "Pacnew / pacsave",
                    f"{n} arquivo(s) pendente(s) de merge", "warning", "diagnostico",
                    count=n, fixable=False)


def check_orphan_packages() -> Finding:
    out = _run(["pacman", "-Qtdq"])
    lines = [l for l in out.splitlines() if l.strip()]
    n = len(lines)
    if n == 0:
        return Finding("orphans", "Pacotes órfãos", "Nenhuma dependência órfã",
                        "ok", "diagnostico")
    return Finding("orphans", "Pacotes órfãos", f"{n} pacote(s) sem dependentes",
                    "warning", "diagnostico", count=n, fixable=True)


def check_orphan_kernels() -> Finding:
    """Detecta kernels instalados que não são o kernel em execução.
    Não decide sozinho que é 'lixo' — múltiplos kernels podem ser
    intencionais — só sinaliza pra revisão manual."""
    running = _run(["uname", "-r"])
    out = _run(["pacman", "-Qq"])
    installed = [l for l in out.splitlines() if re.match(r"^linux(-lts|-zen|-hardened)?$", l.strip())]
    idle = [pkg for pkg in installed if pkg not in running]
    if not idle or len(installed) <= 1:
        return Finding("orphan_kernels", "Kernels órfãos", "Nenhum kernel parado ocupando espaço",
                        "ok", "diagnostico")
    return Finding("orphan_kernels", "Kernels órfãos",
                    f"{', '.join(idle)} instalado(s) sem uso — ocupam /boot",
                    "warning", "diagnostico", count=len(idle), fixable=True)


def check_missing_log_dirs() -> Finding:
    missing = [d for d in EXPECTED_LOG_DIRS if not Path(d).is_dir()]
    if not missing:
        return Finding("log_dirs", "Diretórios de log", "Todos presentes",
                        "ok", "diagnostico")
    return Finding("log_dirs", "Diretórios de log ausentes",
                    f"{len(missing)} diretório(s) faltando (causa comum de 'missing file' falso positivo)",
                    "warning", "diagnostico", count=len(missing), fixable=True)


def check_critical_timers() -> Finding:
    broken = []
    for timer in CRITICAL_TIMERS:
        state = _run(["systemctl", "is-enabled", timer])
        active = _run(["systemctl", "is-active", timer])
        if "enabled" not in state or active != "active" and active != "waiting":
            broken.append(timer)
    if not broken:
        return Finding("critical_timers", "Automação essencial",
                        "paccache / reflector / keyring-sync ativos", "ok", "automacao")
    return Finding("critical_timers", "Automação essencial parada",
                    f"{', '.join(broken)} não está ativo — risco de update quebrar",
                    "critical", "automacao", count=len(broken))


def check_volumes_integrity() -> Finding:
    """fsck -n (somente leitura) em partições NÃO montadas — nunca roda
    em algo montado, pra não arriscar corrupção."""
    out = _run(["lsblk", "-nrpo", "NAME,FSTYPE,MOUNTPOINT"])
    problems = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        dev, fstype = parts[0], parts[1]
        mountpoint = parts[2] if len(parts) > 2 else ""
        if mountpoint or fstype not in ("ext4", "vfat", "exfat"):
            continue
        checker = {"ext4": "fsck.ext4", "vfat": "dosfsck", "exfat": "fsck.exfat"}[fstype]
        result = _run(["sudo", "-n", checker, "-n", dev], timeout=30)
        if result and ("error" in result.lower() or "bad" in result.lower()):
            problems.append(dev)
    if not problems:
        return Finding("volumes", "Integridade dos volumes",
                        "fsck (leitura) sem erros nos volumes desmontados",
                        "ok", "diagnostico")
    return Finding("volumes", "Integridade dos volumes",
                    f"Possível problema em: {', '.join(problems)}",
                    "critical", "diagnostico", count=len(problems))


def check_aur_watchlist() -> list[Finding]:
    import glob
    findings = []
    for entry in AUR_WATCHLIST:
        logs = sorted(glob.glob(entry["log_glob"]))
        if not logs:
            findings.append(Finding(f"aur_{entry['package']}", "Watchlist AUR",
                                     f"{entry['package']}: sem log de checagem ainda",
                                     "warning", "automacao"))
            continue
        last_line = Path(logs[-1]).read_text().strip().splitlines()[-1] if Path(logs[-1]).stat().st_size else ""
        is_update = "Nova versão" in last_line
        findings.append(Finding(f"aur_{entry['package']}", "Watchlist AUR",
                                 last_line or f"{entry['package']}: log vazio",
                                 "warning" if is_update else "ok", "automacao"))
    return findings


# ────────────────────────────────────────────────────────────── agregação --

def compute_score(findings: list[Finding]) -> int:
    critical = sum(1 for f in findings if f.level == "critical")
    warning = sum(1 for f in findings if f.level == "warning")
    return max(0, 100 - 15 * critical - 5 * warning)


def run_full_checkup() -> DoctorReport:
    findings = [
        check_failed_services(),
        check_pacnew_pacsave(),
        check_orphan_packages(),
        check_orphan_kernels(),
        check_missing_log_dirs(),
        check_critical_timers(),
        check_volumes_integrity(),
        *check_aur_watchlist(),
    ]
    return DoctorReport(findings=findings, score=compute_score(findings))
