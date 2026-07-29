#!/usr/bin/env python3
"""desktop-leash bridge — Phase 1 observe-only (stdlib + macOS tools).

Loopback only. Sticky arm. Deny-by-default. No click/type in Phase 1.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import uuid
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
VERSION = "0.1.0"
PHASE = 1

# D0 status; D1 observe (arm). D2+ refused in Phase 1.
ALLOWED_ACTIONS = frozenset(
    {
        "desktop.apps",
        "desktop.windows",
        "desktop.displays",
        "desktop.screenshot",
    }
)

ACTION_TIERS = {
    "desktop.apps": 1,
    "desktop.windows": 1,
    "desktop.displays": 1,
    "desktop.screenshot": 1,
}

_lock = threading.Lock()
_arm: dict[str, Any] = {"armed": False, "until": 0.0, "token": ""}

# Import observe from same package dir
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


def status_payload() -> dict[str, Any]:
    with _lock:
        arm = dict(_arm)
    return {
        "ok": True,
        "bridge": "up",
        "service": "desktop-leash",
        "version": VERSION,
        "phase": PHASE,
        "phase_name": "observe-only",
        "armed": _arm_active(),
        "arm_until": arm.get("until"),
        "arm_mode": "toggle" if ARM_TTL_SEC <= 0 else f"timed_{ARM_TTL_SEC}s",
        "allowed_actions": sorted(ALLOWED_ACTIONS),
        "action_tiers": dict(ACTION_TIERS),
        "permission_doc": "docs/PERMISSION_TIERS.md",
        "plan": str(Path.home() / "ops/DESKTOP_LEASH_PLAN.md"),
        "note": "Phase 1: no click/type/focus. ARM sticky until DISARM.",
    }


def run_action(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "").strip()
    if action in ("", "status"):
        return status_payload()

    if action not in ALLOWED_ACTIONS:
        # Explicit refuse of future tiers
        if action.startswith("desktop.") and action not in ALLOWED_ACTIONS:
            _receipt("deny", {"action": action, "reason": "PHASE1_LOCKED"})
            return {
                "ok": False,
                "code": "PHASE1_LOCKED",
                "detail": f"{action!r} not available in Phase 1 (observe-only). See plan.",
            }
        _receipt("deny", {"action": action, "reason": "UNKNOWN_ACTION"})
        return {"ok": False, "code": "UNKNOWN_ACTION", "detail": f"unknown action {action!r}"}

    if not _arm_active():
        _receipt("deny", {"action": action, "reason": "NOT_ARMED"})
        return {
            "ok": False,
            "code": "NOT_ARMED",
            "detail": "desktop-leash must be ARMED (client arm / POST /v1/arm) before observe actions",
        }

    job_id = str(uuid.uuid4())
    _receipt("enqueue", {"id": job_id, "action": action})

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
    else:
        res = {"ok": False, "code": "UNKNOWN_ACTION", "detail": action}

    res = {**res, "id": job_id, "action": action}
    _receipt("result", {"id": job_id, "action": action, "ok": res.get("ok"), "code": res.get("code")})
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
    print(f"arm_mode={'toggle' if ARM_TTL_SEC <= 0 else ARM_TTL_SEC} version={VERSION}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", flush=True)


if __name__ == "__main__":
    main()
