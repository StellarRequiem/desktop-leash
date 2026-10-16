"""Desktop layout model — window bounds, display geometry, coordinate transforms.

The failure mode this fixes: agents clicking full-screen coords while Terminal
and Chrome split the display. Always resolve *window frames* first, then click
in window-local or normalized (0–1) space.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from observe import _as_str, _run, frontmost_app, screenshot


def display_geometry() -> dict[str, Any]:
    """Main display size via screencapture-friendly bounds (points)."""
    # NSScreen-free: parse system_profiler + fallback 1920x1080
    code, out, err = _run(
        ["system_profiler", "SPDisplaysDataType", "-json"],
        timeout=20.0,
    )
    width, height = 1920, 1080
    names: list[str] = []
    if code == 0:
        try:
            data = json.loads(out)
            for gpu in data.get("SPDisplaysDataType") or []:
                for d in gpu.get("spdisplays_ndrvs") or []:
                    names.append(str(d.get("_name") or "display"))
                    res = d.get("spdisplays_resolution") or d.get("_spdisplays_resolution") or ""
                    # e.g. "1920 x 1080 @ 120Hz" or "1920 x 1080"
                    if isinstance(res, str) and "x" in res:
                        parts = res.replace("@", " ").split()
                        nums = [p for p in parts if p.isdigit()]
                        if len(nums) >= 2:
                            width, height = int(nums[0]), int(nums[1])
        except Exception:
            pass
    return {
        "ok": True,
        "code": "DISPLAY_GEOMETRY",
        "data": {
            "main": {"x": 0, "y": 0, "w": width, "h": height},
            "count": max(1, len(names)) if names else 1,
            "names": names or ["main"],
            "coord_space": "top-left origin, points (not necessarily retina pixels)",
        },
    }


def list_windows_geometry(max_per_app: int = 12) -> dict[str, Any]:
    """Windows with {app, title, x, y, w, h} via System Events."""
    max_per_app = max(1, min(int(max_per_app or 12), 30))
    script = f"""
set maxN to {max_per_app}
set out to ""
tell application "System Events"
  set procs to every process whose background only is false
  repeat with p in procs
    try
      set pname to name of p
      set isFront to frontmost of p
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
        try
          set pos to position of w
          set sz to size of w
          set px to item 1 of pos
          set py to item 2 of pos
          set sw to item 1 of sz
          set sh to item 2 of sz
        on error
          set px to -1
          set py to -1
          set sw to -1
          set sh to -1
        end try
        set out to out & pname & tab & t & tab & px & tab & py & tab & sw & tab & sh & tab & isFront & linefeed
      end repeat
    end try
  end repeat
end tell
return out
"""
    code, out, err = _run(["osascript", "-e", script], timeout=20.0)
    windows: list[dict[str, Any]] = []
    if code == 0 and out.strip():
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            app, title, xs, ys, ws, hs, fr = parts[:7]
            try:
                x, y, w, h = int(float(xs)), int(float(ys)), int(float(ws)), int(float(hs))
            except ValueError:
                x = y = w = h = -1
            windows.append(
                {
                    "app": app.strip(),
                    "title": title.strip()[:200],
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "frontmost": str(fr).strip().lower() in ("true", "1"),
                    "valid_bounds": x >= 0 and y >= 0 and w > 0 and h > 0,
                }
            )
    fm = frontmost_app()
    front_app = (fm.get("data") or {}).get("app") if fm.get("ok") else None
    # Mark frontmost window of front app
    for win in windows:
        if front_app and win["app"] == front_app and win.get("frontmost"):
            win["is_key_window"] = True
        else:
            win["is_key_window"] = bool(win.get("frontmost") and win["app"] == front_app)

    return {
        "ok": True,
        "code": "WINDOWS_GEOMETRY",
        "data": {
            "windows": windows,
            "count": len(windows),
            "frontmost_app": front_app,
            "source": "system_events" if windows else "empty",
            "hint": None
            if windows
            else "Grant Accessibility to the process running desktop-leash for window bounds",
            "osascript_detail": (err or "")[:200] if code != 0 else "",
        },
    }


def layout_snapshot(out_path: Path | None = None) -> dict[str, Any]:
    """Full layout: display + windows geometry + optional full screenshot."""
    disp = display_geometry()
    wins = list_windows_geometry()
    shot = None
    if out_path is not None:
        shot = screenshot(Path(out_path))
    data = {
        "display": (disp.get("data") or {}),
        "windows": (wins.get("data") or {}).get("windows") or [],
        "frontmost_app": (wins.get("data") or {}).get("frontmost_app"),
        "screenshot": (shot.get("data") if shot and shot.get("ok") else shot),
        "control_rule": (
            "Never guess full-screen click coords. "
            "Use desktop.layout, pick a window, then desktop.click_window with rel_x/rel_y in 0..1 "
            "or local_x/local_y inside that window frame."
        ),
    }
    # Quick map of apps → frames for agents
    by_app: dict[str, list[dict[str, int]]] = {}
    for w in data["windows"]:
        if not w.get("valid_bounds"):
            continue
        by_app.setdefault(w["app"], []).append(
            {"x": w["x"], "y": w["y"], "w": w["w"], "h": w["h"], "title": w.get("title") or ""}
        )
    data["frames_by_app"] = by_app
    return {"ok": True, "code": "LAYOUT", "data": data}


def find_window(
    app: str,
    *,
    title_contains: str = "",
    prefer_frontmost: bool = True,
) -> dict[str, Any] | None:
    wins = (list_windows_geometry().get("data") or {}).get("windows") or []
    app_l = app.strip().lower()
    title_l = (title_contains or "").strip().lower()
    candidates = [
        w
        for w in wins
        if w.get("valid_bounds")
        and app_l in (w.get("app") or "").lower()
        and (not title_l or title_l in (w.get("title") or "").lower())
    ]
    if not candidates:
        return None
    if prefer_frontmost:
        for w in candidates:
            if w.get("frontmost") or w.get("is_key_window"):
                return w
    # Largest window
    return max(candidates, key=lambda w: int(w.get("w") or 0) * int(w.get("h") or 0))


def resolve_click_point(
    *,
    app: str,
    rel_x: float | None = None,
    rel_y: float | None = None,
    local_x: int | None = None,
    local_y: int | None = None,
    title_contains: str = "",
) -> dict[str, Any]:
    """Map window-local or normalized coords → global screen point."""
    win = find_window(app, title_contains=title_contains)
    if not win:
        return {
            "ok": False,
            "code": "WINDOW_NOT_FOUND",
            "detail": f"no valid bounds for app={app!r} title~={title_contains!r}",
        }
    wx, wy, ww, wh = int(win["x"]), int(win["y"]), int(win["w"]), int(win["h"])
    if local_x is not None and local_y is not None:
        gx = wx + int(local_x)
        gy = wy + int(local_y)
        mode = "local"
    elif rel_x is not None and rel_y is not None:
        rx = max(0.0, min(1.0, float(rel_x)))
        ry = max(0.0, min(1.0, float(rel_y)))
        # Inset slightly so 0/1 don't hit resize edges
        gx = wx + int(rx * max(1, ww - 1))
        gy = wy + int(ry * max(1, wh - 1))
        mode = "relative"
    else:
        return {
            "ok": False,
            "code": "COORDS_REQUIRED",
            "detail": "provide rel_x+rel_y (0..1) or local_x+local_y",
        }
    return {
        "ok": True,
        "code": "RESOLVED",
        "data": {
            "global_x": gx,
            "global_y": gy,
            "mode": mode,
            "window": win,
        },
    }


def screenshot_window(app: str, out_path: Path, *, title_contains: str = "") -> dict[str, Any]:
    """Capture one window frame via screencapture -R."""
    win = find_window(app, title_contains=title_contains)
    if not win:
        return {
            "ok": False,
            "code": "WINDOW_NOT_FOUND",
            "detail": f"no window for {app!r}",
        }
    x, y, w, h = int(win["x"]), int(win["y"]), int(win["w"]), int(win["h"])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # screencapture -R x,y,w,h (absolute path — thin PATH under launchd)
    from screencap_util import screencapture_bin

    bin_path = screencapture_bin()
    cmd = [bin_path, "-x", "-R", f"{x},{y},{w},{h}", str(out_path)]
    code, _out, err = _run(cmd, timeout=60.0)
    if code != 0 or not out_path.is_file() or out_path.stat().st_size < 32:
        return {
            "ok": False,
            "code": "WINDOW_SHOT_FAIL",
            "detail": (err or f"exit {code}")[:300],
            "window": win,
            "bin": bin_path,
        }
    return {
        "ok": True,
        "code": "WINDOW_SCREENSHOT",
        "data": {
            "path": str(out_path.resolve()),
            "bytes": out_path.stat().st_size,
            "window": win,
            "region": {"x": x, "y": y, "w": w, "h": h},
        },
    }
