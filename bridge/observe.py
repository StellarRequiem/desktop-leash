"""Phase-1 observe helpers — macOS only, no input injection."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any


def _run(cmd: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError as e:
        return 127, "", str(e)


def list_apps() -> dict[str, Any]:
    """Running app-like processes. Prefer System Events; fall back to ps."""
    script = (
        'tell application "System Events" to get name of every process '
        "whose background only is false"
    )
    code, out, err = _run(["osascript", "-e", script], timeout=12.0)
    names: list[str] = []
    source = "system_events"
    if code == 0 and out.strip():
        # osascript may return comma-separated list
        raw = out.replace(", ", "\n")
        names = [n.strip() for n in raw.splitlines() if n.strip()]
        if len(names) == 1 and "," in names[0]:
            names = [n.strip() for n in names[0].split(",") if n.strip()]
    if not names:
        source = "ps_fallback"
        code2, out2, err2 = _run(["ps", "-axc", "-o", "comm="], timeout=5.0)
        if code2 != 0:
            return {
                "ok": False,
                "code": "APPS_FAIL",
                "detail": (err or err2 or "empty").strip(),
                "hint": "Grant Accessibility for full GUI app names (System Events)",
            }
        # Heuristic: title-case / app-like names, drop kernel helpers
        skip = {"loginwindow", "WindowServer", "kernel_task", "launchd", "cfprefsd"}
        for line in out2.splitlines():
            n = line.strip()
            if not n or n in skip or n.startswith("."):
                continue
            if n[0].isupper() or n.endswith(".app") or " " in n:
                names.append(n.replace(".app", ""))
        names = sorted(set(names), key=str.lower)[:80]
    else:
        names = sorted(set(names), key=str.lower)
    return {
        "ok": True,
        "code": "APPS",
        "data": {"apps": names, "count": len(names), "source": source},
    }


def list_windows(max_per_app: int = 20) -> dict[str, Any]:
    """Visible windows: app name + window title (redact nothing yet; titles may be sensitive)."""
    script = f"""
    set maxN to {int(max_per_app)}
    set out to ""
    tell application "System Events"
      set procs to every process whose background only is false
      repeat with p in procs
        set pname to name of p
        try
          set wins to windows of p
          set i to 0
          repeat with w in wins
            set i to i + 1
            if i > maxN then exit repeat
            try
              set t to name of w
            on error
              set t to "(untitled)"
            end try
            set out to out & pname & "\\t" & t & linefeed
          end repeat
        end try
      end repeat
    end tell
    return out
    """
    code, out, err = _run(["osascript", "-e", script], timeout=15.0)
    rows = []
    if code == 0:
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            if "\t" in line:
                app, title = line.split("\t", 1)
            else:
                app, title = line, ""
            rows.append({"app": app.strip(), "title": title.strip()[:200]})
    if not rows:
        # Soft ok with empty + hint (Accessibility often not granted yet)
        return {
            "ok": True,
            "code": "WINDOWS",
            "data": {
                "windows": [],
                "count": 0,
                "source": "empty",
                "hint": "If empty: System Settings → Privacy & Security → Accessibility → enable Terminal/python for this bridge",
                "osascript_detail": (err or out or f"exit {code}")[:200],
            },
        }
    return {
        "ok": True,
        "code": "WINDOWS",
        "data": {"windows": rows, "count": len(rows), "source": "system_events"},
    }


def list_displays() -> dict[str, Any]:
    """Best-effort display count via system_profiler (no arm needed for status extras)."""
    code, out, err = _run(
        ["system_profiler", "SPDisplaysDataType", "-json"],
        timeout=20.0,
    )
    if code != 0:
        return {"ok": False, "code": "DISPLAYS_FAIL", "detail": err or out}
    try:
        data = json.loads(out)
        sp = data.get("SPDisplaysDataType") or []
        n = 0
        names = []
        for gpu in sp:
            for d in gpu.get("spdisplays_ndrvs") or []:
                n += 1
                names.append(d.get("_name") or d.get("spdisplays_name") or "display")
        return {"ok": True, "code": "DISPLAYS", "data": {"count": n or 1, "names": names}}
    except json.JSONDecodeError:
        return {"ok": True, "code": "DISPLAYS", "data": {"count": 1, "names": ["unknown"]}}


def screenshot(out_path: Path, *, interactive: bool = False) -> dict[str, Any]:
    """Capture screen to PNG. Requires Screen Recording permission for this process."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # -x = no sound; full display
    cmd = ["screencapture", "-x"]
    if interactive:
        cmd.append("-i")  # not for agent default
    cmd.append(str(out_path))
    code, _out, err = _run(cmd, timeout=60.0)
    if code != 0 or not out_path.is_file() or out_path.stat().st_size < 32:
        return {
            "ok": False,
            "code": "SCREENSHOT_FAIL",
            "detail": err.strip() or f"exit {code} or empty file",
            "hint": "System Settings → Privacy & Security → Screen Recording → allow Terminal/python (or the app hosting the bridge)",
            "path": str(out_path),
        }
    return {
        "ok": True,
        "code": "SCREENSHOT",
        "data": {
            "path": str(out_path.resolve()),
            "bytes": out_path.stat().st_size,
            "ts": time.time(),
        },
    }
