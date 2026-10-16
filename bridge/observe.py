"""macOS observe + Phase-2 input helpers (System Events / Accessibility)."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

# Escape for AppleScript string literals
def _as_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


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


def frontmost_app() -> dict[str, Any]:
    script = (
        'tell application "System Events" to get name of first application process '
        "whose frontmost is true"
    )
    code, out, err = _run(["osascript", "-e", script], timeout=8.0)
    if code != 0 or not out.strip():
        return {
            "ok": False,
            "code": "FRONTMOST_FAIL",
            "detail": (err or out or f"exit {code}").strip(),
        }
    return {"ok": True, "code": "FRONTMOST", "data": {"app": out.strip()}}


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
    from screencap_util import screencapture_bin

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # -x = no sound; full display
    bin_path = screencapture_bin()
    cmd = [bin_path, "-x"]
    if interactive:
        cmd.append("-i")  # not for agent default
    cmd.append(str(out_path))
    code, _out, err = _run(cmd, timeout=60.0)
    if code != 0 or not out_path.is_file() or out_path.stat().st_size < 32:
        return {
            "ok": False,
            "code": "SCREENSHOT_FAIL",
            "detail": err.strip() or f"exit {code} or empty file",
            "hint": (
                "System Settings → Privacy & Security → Screen Recording → allow the app "
                "hosting desktop-leash (Terminal/python). Binary: " + bin_path
            ),
            "path": str(out_path),
            "bin": bin_path,
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


# --- Phase 2 input (allowlist enforced by server before call) ---

def focus_app(app_name: str) -> dict[str, Any]:
    """Activate an application by process/app name."""
    name = app_name.strip()
    if not name or len(name) > 80:
        return {"ok": False, "code": "BAD_APP", "detail": "invalid app name"}
    # Prefer process name activate via System Events (works when app name matches)
    script = f'''
    tell application "System Events"
      set frontmost of first process whose name is "{_as_str(name)}" to true
    end tell
    '''
    code, out, err = _run(["osascript", "-e", script], timeout=10.0)
    if code != 0:
        # Fallback: tell application "X" to activate
        script2 = f'tell application "{_as_str(name)}" to activate'
        code2, out2, err2 = _run(["osascript", "-e", script2], timeout=10.0)
        if code2 != 0:
            return {
                "ok": False,
                "code": "FOCUS_FAIL",
                "detail": (err or err2 or out or out2).strip()[:300],
            }
    time.sleep(0.25)
    fm = frontmost_app()
    return {
        "ok": True,
        "code": "FOCUSED",
        "data": {
            "requested": name,
            "frontmost": (fm.get("data") or {}).get("app"),
        },
    }


def click_xy(x: int, y: int) -> dict[str, Any]:
    """Click screen coordinates (global). Requires Accessibility."""
    x, y = int(x), int(y)
    if not (0 <= x <= 10000 and 0 <= y <= 10000):
        return {"ok": False, "code": "BAD_COORDS", "detail": f"out of range {x},{y}"}
    script = f'tell application "System Events" to click at {{{x}, {y}}}'
    code, out, err = _run(["osascript", "-e", script], timeout=8.0)
    if code != 0:
        return {
            "ok": False,
            "code": "CLICK_FAIL",
            "detail": (err or out).strip()[:300],
            "hint": "Accessibility required; coordinates are global screen pixels",
        }
    return {"ok": True, "code": "CLICKED", "data": {"x": x, "y": y}}


def type_text(text: str) -> dict[str, Any]:
    """Type into frontmost app via keystroke. No newlines as execute — use press for Return."""
    if not isinstance(text, str) or not text:
        return {"ok": False, "code": "EMPTY_TEXT", "detail": "text required"}
    if len(text) > 2000:
        return {"ok": False, "code": "TEXT_TOO_LONG", "detail": "max 2000 chars per type"}
    # Block only pure control abuse; Return not in keystroke string
    if "\n" in text or "\r" in text:
        return {
            "ok": False,
            "code": "NO_NEWLINE",
            "detail": "newlines not allowed in type; use desktop.press Return separately (and only if intentional)",
        }
    # Escape for AppleScript
    esc = _as_str(text)
    script = f'tell application "System Events" to keystroke "{esc}"'
    code, out, err = _run(["osascript", "-e", script], timeout=15.0)
    if code != 0:
        return {
            "ok": False,
            "code": "TYPE_FAIL",
            "detail": (err or out).strip()[:300],
            "hint": "Accessibility required; focus an allowlisted app first",
        }
    return {
        "ok": True,
        "code": "TYPED",
        "data": {"len": len(text), "preview": text[:40]},
    }


# Common key → System Events key code
_KEY_CODES = {
    "return": 36,
    "enter": 36,
    "tab": 48,
    "escape": 53,
    "esc": 53,
    "delete": 51,
    "backspace": 51,
    "space": 49,
    "up": 126,
    "down": 125,
    "left": 123,
    "right": 124,
    "pageup": 116,
    "pagedown": 121,
}


def press_key(key: str) -> dict[str, Any]:
    k = (key or "").strip().lower()
    if k not in _KEY_CODES:
        return {
            "ok": False,
            "code": "BAD_KEY",
            "detail": f"unsupported key {key!r}; allow: {sorted(_KEY_CODES)}",
        }
    code_n = _KEY_CODES[k]
    script = f"tell application \"System Events\" to key code {code_n}"
    code, out, err = _run(["osascript", "-e", script], timeout=8.0)
    if code != 0:
        return {"ok": False, "code": "PRESS_FAIL", "detail": (err or out).strip()[:300]}
    return {"ok": True, "code": "PRESSED", "data": {"key": k, "key_code": code_n}}


def scroll_dy(dy: int) -> dict[str, Any]:
    """Approximate scroll via page up/down keys (reliable without AX scroll areas)."""
    dy = int(dy)
    if dy == 0:
        return {"ok": True, "code": "SCROLLED", "data": {"dy": 0, "method": "noop"}}
    steps = min(abs(dy) // 100 or 1, 12)
    key = "pagedown" if dy > 0 else "pageup"
    for _ in range(steps):
        r = press_key(key)
        if not r.get("ok"):
            return r
        time.sleep(0.05)
    return {"ok": True, "code": "SCROLLED", "data": {"dy": dy, "steps": steps, "method": key}}


def quit_app(app_name: str) -> dict[str, Any]:
    """Quit an application (D4 high-blast — confirm required by server)."""
    name = app_name.strip()
    if not name or len(name) > 80:
        return {"ok": False, "code": "BAD_APP", "detail": "invalid app name"}
    script = f'tell application "{_as_str(name)}" to quit'
    code, out, err = _run(["osascript", "-e", script], timeout=15.0)
    if code != 0:
        return {
            "ok": False,
            "code": "QUIT_FAIL",
            "detail": (err or out).strip()[:300],
        }
    return {"ok": True, "code": "QUIT", "data": {"app": name}}


def ax_snapshot(max_elements: int = 40) -> dict[str, Any]:
    """Shallow Accessibility UI tree for frontmost app (redacted).

    Phase 5 observe. Titles truncated; secure fields redacted.
    Requires Accessibility permission.
    """
    max_elements = max(1, min(int(max_elements or 40), 60))
    script = f"""
set maxN to {max_elements}
tell application "System Events"
  set frontProc to first application process whose frontmost is true
  set appName to name of frontProc
  try
    set win to first window of frontProc
    set winTitle to name of win
  on error
    set winTitle to ""
    return appName & linefeed & winTitle
  end try
  set linesOut to {{}}
  try
    set uiList to UI elements of win
    set n to 0
    repeat with u in uiList
      set n to n + 1
      if n > maxN then exit repeat
      try
        set r to role of u as string
      on error
        set r to "?"
      end try
      try
        set t to name of u as string
      on error
        set t to ""
      end try
      try
        set d to description of u as string
      on error
        set d to ""
      end try
      set v to ""
      if r is "secure text field" then
        set v to "[redacted-secure]"
      else
        try
          set v to value of u as string
        end try
      end if
      if (length of t) > 50 then set t to text 1 thru 50 of t
      if (length of d) > 50 then set d to text 1 thru 50 of d
      if (length of v) > 40 then set v to text 1 thru 40 of v
      set end of linesOut to r & tab & t & tab & d & tab & v
    end repeat
  end try
end tell
set AppleScript's text item delimiters to linefeed
return appName & linefeed & winTitle & linefeed & (linesOut as text)
"""
    code, out, err = _run(["osascript", "-e", script], timeout=18.0)
    if code != 0:
        return {
            "ok": False,
            "code": "AX_FAIL",
            "detail": (err or out or f"exit {code}").strip()[:400],
            "hint": "Grant Accessibility to the process running desktop-leash",
        }
    lines = [ln for ln in (out or "").splitlines()]
    app = lines[0] if lines else ""
    win = lines[1] if len(lines) > 1 else ""
    elements: list[dict[str, str]] = []
    for ln in lines[2:]:
        parts = ln.split("\t")
        while len(parts) < 4:
            parts.append("")
        role, title, desc, val = parts[0], parts[1], parts[2], parts[3]
        elements.append(
            {
                "role": role[:40],
                "title": title[:60],
                "description": desc[:60],
                "value": val[:40],
            }
        )
    return {
        "ok": True,
        "code": "AX_SNAPSHOT",
        "data": {
            "app": app,
            "window": win[:120],
            "elements": elements,
            "count": len(elements),
            "redacted": True,
        },
    }
