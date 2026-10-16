"""Resolve macOS screencapture binary — launchd/bridged Python often has a thin PATH."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# Standard locations on macOS (screencapture is not always on minimal PATH).
# Prefer absolute paths so thin PATH never becomes bare "screencapture".
_CANDIDATES = (
    "/usr/sbin/screencapture",
    "/usr/bin/screencapture",
    "/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Support/screencapture",
)


def screencapture_bin() -> str:
    for p in _CANDIDATES:
        try:
            path = Path(p)
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
        except OSError:
            continue
    # Expand PATH for which() under launchd
    env_path = os.environ.get("PATH") or ""
    for extra in ("/usr/sbin", "/usr/bin", "/bin", "/sbin"):
        if extra not in env_path.split(os.pathsep):
            env_path = extra + os.pathsep + env_path
    found = shutil.which("screencapture", path=env_path)
    if found:
        return found
    # Prefer absolute candidate even if execute bit probe failed (SIP / ACL edge)
    for p in _CANDIDATES[:2]:
        if Path(p).exists():
            return p
    return "/usr/sbin/screencapture"
