from __future__ import annotations

import json
import os
import subprocess

HELPER_PATH = "/usr/local/bin/carbonara-helper"


def invoke_helper(action: str, args: dict | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    """Dispara `pkexec carbonara-helper <DISPLAY> <XAUTHORITY> <ação> <json>`,
    seguindo exatamente o formato documentado no próprio carbonara-helper.
    Reaproveitável por qualquer página que precise de uma ação privilegiada
    registrada no ACTIONS dict do helper."""
    display = os.environ.get("DISPLAY", "")
    xauthority = os.environ.get("XAUTHORITY", "")
    payload = json.dumps(args or {})
    cmd = ["pkexec", HELPER_PATH, display, xauthority, action, payload]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
