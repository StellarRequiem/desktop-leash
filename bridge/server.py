#!/usr/bin/env python3
"""desktop-leash bridge — Phase 2 allowlisted input (stdlib + macOS tools).

Loopback only. Sticky arm. Deny-by-default. App allowlist for D2/D3.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = ROOT / "receipts"
CAPTURES = ROOT / "captures"
STATE_PATH = Path(__file__).resolve().parent / ".state.json"
HOST = "127.0.0.1"
PORT = int(os.environ.get("DESKTOP_LEASH_PORT", "8757"))
ARM_TTL_SEC = int(os.environ.get("DESKTOP_LEASH_ARM_TTL", "0"))  # 0 = sticky
VERSION = "0.2.0"
PHASE = 2

# Default allowlist — process names as System Events reports them
DEFAULT_APP_ALLOWLIST = frozenset(
    {
        "Terminal",
        "iTerm2",
        "iTerm",
        "Ghostty",
        "Alacritty",
        "kitty",
        "Google Chrome",
        "Chromium",
        "Safari",
        "Firefox",
        "Code",
        "Cursor",
        "TextEdit",
        "Finder",
        "Preview",
        "Notes",
        " syncthing",  # noop guard against empty
    }
)


def _load_allowlist() -> frozenset[str]:
    extra = os.environ.get("DESKTOP_LEASH_ALLOW_APPS", "")
    names = set(DEFAULT_APP_ALLOWLIST)
    names.discard(" syncthing")
    for part in extra.split(","):
        p = part.strip()
        if p:
            names.add(p)
    return frozenset(names)


APP_ALLOWLIST = _load_allowlist()

# Deny even if somehow matched
APP_DENYLIST = frozenset(
    {
        "1Password",
        "1Password 7",
        "Bitwarden",
        "Keychain Access",
        "Wallet",
        "Messages",
        "Mail",
        "Passwords",
    }
)

ALLOWED_ACTIONS = frozenset(
    {
        # D1 observe
        "desktop.apps",
        "desktop.windows",
        "desktop.displays",
        "desktop.screenshot",
        "desktop.frontmost",
        # D2 focus
        "desktop.focus",
        # D3 input
        "desktop.click",
        "desktop.type",
        "desktop.press",
        "desktop.scroll",
    }
)

ACTION_TIERS = {
    "desktop.apps": 1,
    "desktop.windows": 1,
    "desktop.displays": 1,
    "desktop.screenshot": 1,
    "desktop.frontmost": 1,
    "desktop.focus": 2,
    "desktop.click": 3,
    "desktop.type": 3,
    "desktop.press": 3,
    "desktop.scroll": 3,
}

# Velocity: max input events per window
VEL_MAX = int(os.environ.get("DESKTOP_LEASH_VEL_MAX", "40"))
VEL_WINDOW = float(os.environ.get("DESKTOP_LEASH_VEL_WINDOW", "60"))

_lock = threading.Lock()
_arm: dict[str, Any] = {"armed": False, "until": 0.0, "token": ""}
_vel: dict[str, deque[float]] = defaultdict(deque)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import observe  # noqa: E402


def _now() -> float:
    return time.time()


def _receipt(kind: str, body: dict[str, Any]) -> None:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    path = RECEIPTS / f"{time.strftime('%Y-%m-%d')}.jsonl"
    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind, **body}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")


def _arm_active() -> bool:
    with _lock:
        if not _arm.get("armed"):
            return False
        until = float(_arm.get("until") or 0)
        if until > 0 and _now() > until:
            _arm["armed"] = False
            _arm["until"] = 0.0
            return False
        return True


def _set_arm(armed: bool, ttl: int | None = None) -> dict[str, Any]:
    if ttl is None:
        ttl = ARM_TTL_SEC
    with _lock:
        if armed:
            token = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
            until = 0.0 if int(ttl) <= 0 else _now() + int(ttl)
            _arm.update({"armed": True, "until": until, "token": token})
        else:
            _arm.update({"armed": False, "until": 0.0, "token": ""})
        snap = dict(_arm)
    _receipt(
        "arm",
        {"armed": snap["armed"], "until": snap["until"], "mode": "toggle" if not snap["until"] else "timed"},
    )
    _save_state()
    return snap


def _save_state() -> None:
    with _lock:
        data = {"arm": dict(_arm), "saved_at": _now()}
    try:
        STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _load_state() -> None:
    if not STATE_PATH.is_file():
        return
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        arm = data.get("arm") or {}
        with _lock:
            _arm.update(
                {
                    "armed": bool(arm.get("armed")),
                    "until": float(arm.get("until") or 0),
                    "token": str(arm.get("token") or ""),
                }
            )
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass


def _velocity_ok(bucket: str = "input") -> tuple[bool, str]:
    now = _now()
    with _lock:
        q = _vel[bucket]
        while q and (now - q[0]) > VEL_WINDOW:
            q.popleft()
        if len(q) >= VEL_MAX:
            return False, f"velocity {len(q)}/{VEL_MAX} in {VEL_WINDOW}s"
        q.append(now)
        return True, "ok"


def _app_allowed(name: str) -> bool:
    if not name:
        return False
    if name in APP_DENYLIST:
        return False
    if name in APP_ALLOWLIST:
        return True
    # partial match for "Google Chrome Helper" etc. — only allow exact list for safety
    return False


def _require_frontmost_allowed() -> dict[str, Any] | None:
    """Return error dict if frontmost not allowlisted; else None."""
    fm = observe.frontmost_app()
    if not fm.get("ok"):
        return {
            "ok": False,
            "code": "FRONTMOST_FAIL",
            "detail": fm.get("detail"),
            "hint": "Accessibility required",
        }
    app = (fm.get("data") or {}).get("app") or ""
    if app in APP_DENYLIST:
        return {
            "ok": False,
            "code": "APP_DENIED",
            "detail": f"frontmost app {app!r} is denylisted",
        }
    if not _app_allowed(app):
        return {
            "ok": False,
            "code": "APP_NOT_ALLOWLISTED",
            "detail": f"frontmost app {app!r} not on allowlist",
            "data": {"frontmost": app, "allowlist": sorted(APP_ALLOWLIST)},
        }
    return None


def status_payload() -> dict[str, Any]:
    with _lock:
        arm = dict(_arm)
    return {
        "ok": True,
        "bridge": "up",
        "service": "desktop-leash",
        "version": VERSION,
        "phase": PHASE,
        "phase_name": "allowlisted-input",
        "armed": _arm_active(),
        "arm_until": arm.get("until"),
        "arm_mode": "toggle" if ARM_TTL_SEC <= 0 else f"timed_{ARM_TTL_SEC}s",
        "allowed_actions": sorted(ALLOWED_ACTIONS),
        "action_tiers": dict(ACTION_TIERS),
        "app_allowlist": sorted(APP_ALLOWLIST),
        "app_denylist": sorted(APP_DENYLIST),
        "velocity": {"max": VEL_MAX, "window_sec": VEL_WINDOW},
        "permission_doc": "docs/PERMISSION_TIERS.md",
        "plan": str(Path.home() / "ops/DESKTOP_LEASH_PLAN.md"),
        "note": "Phase 2: focus/click/type/press/scroll only if frontmost app allowlisted. No D4 yet.",
    }


def run_action(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "").strip()
    if action in ("", "status"):
        return status_payload()

    if action not in ALLOWED_ACTIONS:
        if action.startswith("desktop."):
            _receipt("deny", {"action": action, "reason": "PHASE_LOCKED"})
            return {
                "ok": False,
                "code": "PHASE_LOCKED",
                "detail": f"{action!r} not in Phase {PHASE}. See plan for Phase 3+.",
            }
        _receipt("deny", {"action": action, "reason": "UNKNOWN_ACTION"})
        return {"ok": False, "code": "UNKNOWN_ACTION", "detail": f"unknown action {action!r}"}

    if not _arm_active():
        _receipt("deny", {"action": action, "reason": "NOT_ARMED"})
        return {
            "ok": False,
            "code": "NOT_ARMED",
            "detail": "desktop-leash must be ARMED before D1+ actions",
        }

    tier = ACTION_TIERS.get(action, 9)
    job_id = str(uuid.uuid4())
    _receipt("enqueue", {"id": job_id, "action": action, "tier": tier})

    # D3 velocity
    if tier >= 3:
        ok_v, msg_v = _velocity_ok("input")
        if not ok_v:
            _receipt("deny", {"action": action, "reason": "VELOCITY", "detail": msg_v})
            return {"ok": False, "code": "VELOCITY", "detail": msg_v, "id": job_id}

    res: dict[str, Any]

    if action == "desktop.apps":
        res = observe.list_apps()
    elif action == "desktop.windows":
        res = observe.list_windows(max_per_app=int(payload.get("max_per_app") or 20))
    elif action == "desktop.displays":
        res = observe.list_displays()
    elif action == "desktop.screenshot":
        out = payload.get("path") or ""
        if not out:
            CAPTURES.mkdir(parents=True, exist_ok=True)
            out = str(CAPTURES / f"shot-{time.strftime('%Y%m%d-%H%M%S')}-{job_id[:8]}.png")
        res = observe.screenshot(Path(out))
    elif action == "desktop.frontmost":
        res = observe.frontmost_app()
    elif action == "desktop.focus":
        app = str(payload.get("app") or "").strip()
        if not _app_allowed(app):
            res = {
                "ok": False,
                "code": "APP_NOT_ALLOWLISTED",
                "detail": f"cannot focus {app!r}",
                "data": {"allowlist": sorted(APP_ALLOWLIST)},
            }
        elif app in APP_DENYLIST:
            res = {"ok": False, "code": "APP_DENIED", "detail": f"{app!r} denylisted"}
        else:
            res = observe.focus_app(app)
    elif action == "desktop.click":
        gate = _require_frontmost_allowed()
        if gate:
            res = gate
        else:
            res = observe.click_xy(int(payload.get("x") or 0), int(payload.get("y") or 0))
    elif action == "desktop.type":
        gate = _require_frontmost_allowed()
        if gate:
            res = gate
        else:
            res = observe.type_text(str(payload.get("text") or ""))
    elif action == "desktop.press":
        gate = _require_frontmost_allowed()
        if gate:
            res = gate
        else:
            key = str(payload.get("key") or "return")
            # Soft-guard: Return into Terminal could execute — still allowed but receipted
            res = observe.press_key(key)
            if res.get("ok") and key.lower() in ("return", "enter"):
                res["warning"] = "Return/Enter may execute focused shell command — use intentionally"
    elif action == "desktop.scroll":
        gate = _require_frontmost_allowed()
        if gate:
            res = gate
        else:
            res = observe.scroll_dy(int(payload.get("dy") or 0))
    else:
        res = {"ok": False, "code": "UNKNOWN_ACTION", "detail": action}

    res = {**res, "id": job_id, "action": action}
    _receipt(
        "result",
        {
            "id": job_id,
            "action": action,
            "ok": res.get("ok"),
            "code": res.get("code"),
        },
    )
    return res


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, code: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/v1/status", "/health", "/"):
            self._json(200, status_payload())
            return
        self._json(404, {"ok": False, "code": "NOT_FOUND"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        body = self._read_body()
        if path == "/v1/action":
            self._json(200, run_action(body))
            return
        if path == "/v1/arm":
            armed = bool(body.get("armed"))
            ttl = body.get("ttl")
            ttl = ARM_TTL_SEC if ttl is None else int(ttl)
            snap = _set_arm(armed, ttl=ttl)
            self._json(
                200,
                {
                    "ok": True,
                    "armed": snap["armed"] and _arm_active(),
                    "until": snap["until"],
                    "mode": "toggle" if not snap["until"] else "timed",
                    "token": snap["token"] if snap["armed"] else "",
                },
            )
            return
        self._json(404, {"ok": False, "code": "NOT_FOUND"})


def main() -> None:
    _load_state()
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"desktop-leash phase {PHASE} on http://{HOST}:{PORT}", flush=True)
    print(
        f"version={VERSION} arm_mode={'toggle' if ARM_TTL_SEC <= 0 else ARM_TTL_SEC} "
        f"allowlist={len(APP_ALLOWLIST)}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", flush=True)


if __name__ == "__main__":
    main()
