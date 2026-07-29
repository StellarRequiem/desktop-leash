"""CUA-depth observe/act helpers (imported by observe/server)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from observe import _as_str, _run, ax_snapshot, frontmost_app, list_apps, screenshot


def region_screenshot(out_path: Path, x: int, y: int, w: int, h: int) -> dict[str, Any]:
    """Capture a screen rectangle. Requires Screen Recording."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    x, y, w, h = int(x), int(y), int(w), int(h)
    if w < 2 or h < 2 or w > 8000 or h > 8000:
        return {"ok": False, "code": "BAD_REGION", "detail": f"{w}x{h}"}
    if x < 0 or y < 0:
        return {"ok": False, "code": "BAD_REGION", "detail": "x,y must be >= 0"}
    cmd = ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", str(out_path)]
    code, _out, err = _run(cmd, timeout=60.0)
    if code != 0 or not out_path.is_file() or out_path.stat().st_size < 32:
        return {
            "ok": False,
            "code": "REGION_SHOT_FAIL",
            "detail": (err or "").strip() or f"exit {code}",
            "path": str(out_path),
        }
    return {
        "ok": True,
        "code": "REGION_SCREENSHOT",
        "data": {
            "path": str(out_path.resolve()),
            "bytes": out_path.stat().st_size,
            "region": {"x": x, "y": y, "w": w, "h": h},
        },
    }


def ax_click(
    *,
    role: str = "",
    title: str = "",
    description: str = "",
    index: int = 1,
) -> dict[str, Any]:
    """Click a UI element of the frontmost window by AX match."""
    role = (role or "").strip()
    title = (title or "").strip()
    description = (description or "").strip()
    index = max(1, min(int(index or 1), 20))
    if not any((role, title, description)):
        return {
            "ok": False,
            "code": "AX_MATCH_REQUIRED",
            "detail": "provide role and/or title and/or description",
        }

    snap = ax_snapshot(max_elements=60)
    if not snap.get("ok"):
        return snap
    data = snap.get("data") or {}
    elements = data.get("elements") or []
    matches: list[tuple[int, dict[str, Any]]] = []
    for i, el in enumerate(elements):
        r = (el.get("role") or "").lower()
        t = (el.get("title") or "").lower()
        d = (el.get("description") or "").lower()
        if "secure" in r or "password" in r or "password" in d:
            continue
        ok = True
        if role and role.lower() not in r:
            ok = False
        if title and title.lower() not in t and title.lower() not in d:
            ok = False
        if description and description.lower() not in d and description.lower() not in t:
            ok = False
        if ok:
            matches.append((i + 1, el))

    if not matches:
        return {
            "ok": False,
            "code": "AX_NO_MATCH",
            "detail": "no UI element matched",
            "data": {
                "app": data.get("app"),
                "tried": {"role": role, "title": title, "description": description},
            },
        }
    if index > len(matches):
        return {
            "ok": False,
            "code": "AX_INDEX",
            "detail": f"index {index} but only {len(matches)} matches",
            "data": {
                "matches": [
                    {
                        "role": m[1].get("role"),
                        "title": m[1].get("title"),
                        "description": m[1].get("description"),
                    }
                    for m in matches[:10]
                ]
            },
        }

    target = matches[index - 1][1]
    t_name = target.get("title") or ""
    t_desc = target.get("description") or ""
    as_index = matches[index - 1][0]

    if t_desc and t_desc not in ("missing value", ""):
        script = (
            'tell application "System Events"\n'
            "  set frontProc to first application process whose frontmost is true\n"
            "  set win to first window of frontProc\n"
            "  try\n"
            f'    click (first UI element of win whose description is "{_as_str(t_desc)}")\n'
            "  on error\n"
            f'    click (first UI element of win whose name is "{_as_str(t_name)}")\n'
            "  end try\n"
            "end tell\n"
        )
    elif t_name and t_name not in ("missing value", ""):
        script = (
            'tell application "System Events"\n'
            "  set frontProc to first application process whose frontmost is true\n"
            "  set win to first window of frontProc\n"
            f'  click (first UI element of win whose name is "{_as_str(t_name)}")\n'
            "end tell\n"
        )
    else:
        script = (
            'tell application "System Events"\n'
            "  set frontProc to first application process whose frontmost is true\n"
            "  set win to first window of frontProc\n"
            f"  set u to UI element {as_index} of win\n"
            "  click u\n"
            "end tell\n"
        )

    code, out, err = _run(["osascript", "-e", script], timeout=12.0)
    if code != 0:
        return {
            "ok": False,
            "code": "AX_CLICK_FAIL",
            "detail": (err or out).strip()[:300],
            "data": {"target": target, "app": data.get("app")},
        }
    return {
        "ok": True,
        "code": "AX_CLICKED",
        "data": {
            "app": data.get("app"),
            "target": target,
            "match_index": index,
            "match_count": len(matches),
        },
    }


def cua_observe_bundle(out_dir: Path | None = None) -> dict[str, Any]:
    """One-shot CUA observe: frontmost + apps + ax + screenshot."""
    out_dir = Path(out_dir or (Path.home() / "desktop-leash" / "captures" / "cua"))
    out_dir.mkdir(parents=True, exist_ok=True)
    shot = out_dir / f"observe-{int(time.time())}.png"
    fm = frontmost_app()
    apps = list_apps()
    ax = ax_snapshot(max_elements=40)
    sc = screenshot(shot)
    return {
        "ok": True,
        "code": "CUA_OBSERVE",
        "data": {
            "frontmost": fm.get("data") if fm.get("ok") else fm,
            "apps": (apps.get("data") or {}).get("apps", [])[:30] if apps.get("ok") else apps,
            "ax": ax.get("data") if ax.get("ok") else ax,
            "screenshot": sc.get("data") if sc.get("ok") else sc,
        },
    }
