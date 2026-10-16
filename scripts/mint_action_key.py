#!/usr/bin/env python3
"""Operator-only: mint a 32-byte desktop action key (mode 0600) for one client_id.

Prints the path only, never the key. Refuses to overwrite and refuses codex's key name.
Usage: mint_action_key.py <client_id>   (grok | claude | ollama | codex-plane)
"""
import os, re, sys
from pathlib import Path

DIR = Path.home() / "Library" / "Application Support" / "AssuranceMesh" / "DesktopProxy-v5"


def mint(client_id: str, directory: Path = DIR) -> Path:
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", client_id) or client_id == "codex":
        raise SystemExit("refused: client_id must be lowercase [a-z0-9_-] and not 'codex'")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"plane-{client_id}-action-key"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, os.urandom(32))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    return path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(mint(sys.argv[1]))
