#!/usr/bin/env python3
"""desktop-leash bridge — Phase 6 CUA depth: AX click, region shot, observe bundle.

Loopback only. Sticky arm. App allowlist. D4 requires human confirm + D4 session.
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
STATE_PATH = Path('/Users/llm01/Library/Application Support/AssuranceMesh/DesktopProxy-v5/bridge-arm-v7.json')
HOST = "127.0.0.1"
PORT = int(os.environ.get("DESKTOP_LEASH_PORT", "8757"))
ARM_TTL_DEFAULT = 900
ARM_TTL_MAX = 86400


def _clamp_arm_ttl(value: Any) -> int:
    """Arming always expires. 0/negative/garbage -> default; above max -> max."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return ARM_TTL_DEFAULT
    if v <= 0:
        return ARM_TTL_DEFAULT
    return min(v, ARM_TTL_MAX)


ARM_TTL_SEC = _clamp_arm_ttl(os.environ.get("DESKTOP_LEASH_ARM_TTL", str(ARM_TTL_DEFAULT)))
# D4 confirm required by default; set DESKTOP_LEASH_REQUIRE_CONFIRM=0 to disable (not recommended)
REQUIRE_D4_CONFIRM = os.environ.get("DESKTOP_LEASH_REQUIRE_CONFIRM", "1") not in (
    "0",
    "false",
    "no",
)
CONFIRM_TTL_SEC = int(os.environ.get("DESKTOP_LEASH_CONFIRM_TTL", "120"))
# Dual-control: D4 also needs an open D4 session (operator arms separately)
D4_SESSION_DEFAULT_TTL = int(os.environ.get("DESKTOP_LEASH_D4_SESSION_TTL", "300"))
REQUIRE_D4_SESSION = os.environ.get("DESKTOP_LEASH_REQUIRE_D4_SESSION", "1") not in (
    "0",
    "false",
    "no",
)
VERSION = "0.7.0"
PHASE = 7
# Profile: strict | cua (default cua = wider productive apps)
PROFILE = os.environ.get("DESKTOP_LEASH_PROFILE", "cua").strip().lower() or "cua"

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
    }
)


def _load_profile_extras() -> frozenset[str]:
    """Load CUA extra allowlist from profiles/cua_allowlist.json when profile=cua."""
    if PROFILE not in ("cua", "wide", "full"):
        return frozenset()
    path = ROOT / "profiles" / "cua_allowlist.json"
    if not path.is_file():
        return frozenset()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        names = data.get("extra_allowlist") or []
        return frozenset(str(n).strip() for n in names if str(n).strip())
    except Exception:
        return frozenset()


def _load_allowlist() -> frozenset[str]:
    extra = os.environ.get("DESKTOP_LEASH_ALLOW_APPS", "")
    names = set(DEFAULT_APP_ALLOWLIST)
    names |= set(_load_profile_extras())
    for part in extra.split(","):
        p = part.strip()
        if p:
            names.add(p)
    return frozenset(names)


APP_ALLOWLIST = _load_allowlist()

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
        "Coinbase",
        "Ledger Live",
        "Authy",
        "Microsoft Authenticator",
    }
)


# Operator-selected capability mode. A missing/malformed policy stops startup.
def _operator_proxy_policy():
    path = ROOT / "profiles" / "cua_allowlist.json"
    raw = path.read_bytes()
    value = json.loads(raw)
    mode = value.get("input_scope", "allowlist")
    if mode not in ("allowlist", "operator-proxy"):
        raise RuntimeError("INVALID_INPUT_SCOPE")
    if mode == "operator-proxy" and value.get("operator_authorization") != "desktop-proxy-20261012":
        raise RuntimeError("PROXY_AUTHORITY_REQUIRED")
    return mode, hashlib.sha256(raw).hexdigest()

INPUT_SCOPE, INPUT_POLICY_SHA = _operator_proxy_policy()

def _input_policy_current():
    try:
        return _operator_proxy_policy() == (INPUT_SCOPE, INPUT_POLICY_SHA)
    except Exception:
        return False

def _app_denied(name):
    # Denylist always wins, in every input_scope (operator-proxy included).
    return name in APP_DENYLIST

# Apps we never quit even if allowlisted (safety)
QUIT_DENY = frozenset({"Finder", "WindowServer", "loginwindow", "Dock", "SystemUIServer"})

ALLOWED_ACTIONS = frozenset(
    {
        "desktop.apps",
        "desktop.windows",
        "desktop.displays",
        "desktop.screenshot",
        "desktop.frontmost",
        "desktop.focus",
        "desktop.click",
        "desktop.type",
        "desktop.press",
        "desktop.scroll",
        "desktop.quit",  # D4
        "desktop.ax",  # Phase 5 observe
        "desktop.ax_click",  # Phase 6 CUA
        "desktop.region_screenshot",
        "desktop.cua_observe",
        "desktop.layout",
        "desktop.click_window",
        "desktop.screenshot_window",
    }
)

ACTION_TIERS = {
    "desktop.apps": 1,
    "desktop.windows": 1,
    "desktop.displays": 1,
    "desktop.screenshot": 1,
    "desktop.frontmost": 1,
    "desktop.ax": 1,
    "desktop.region_screenshot": 1,
    "desktop.cua_observe": 1,
    "desktop.layout": 1,
    "desktop.screenshot_window": 1,
    "desktop.click_window": 3,
    "desktop.focus": 2,
    "desktop.ax_click": 3,
    "desktop.click": 3,
    "desktop.type": 3,
    "desktop.press": 3,  # may escalate to 4 for return/enter
    "desktop.scroll": 3,
    "desktop.quit": 4,
}

HIGH_BLAST_KEYS = frozenset({"return", "enter"})

VEL_MAX = int(os.environ.get("DESKTOP_LEASH_VEL_MAX", "40"))
VEL_WINDOW = float(os.environ.get("DESKTOP_LEASH_VEL_WINDOW", "60"))

_lock = threading.Lock()
_arm: dict[str, Any] = {"armed": False, "until": 0.0, "token": ""}
# Dual-control window for D4 (separate from sticky arm)
_d4_session: dict[str, Any] = {"open": False, "until": 0.0}
_vel: dict[str, deque[float]] = defaultdict(deque)
# pending confirms: id -> {action, payload, created, summary, tier}
_pending: dict[str, dict[str, Any]] = {}

sys.path.insert(0, str(Path(__file__).resolve().parent))
import observe  # noqa: E402
import observe_cua  # noqa: E402
import layout  # noqa: E402
import proxy_input


def _now() -> float:
    return time.time()


def _receipt(kind: str, body: dict[str, Any]) -> None:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    path = RECEIPTS / f"{time.strftime('%Y-%m-%d')}.jsonl"
    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind, **body}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")


def _d4_session_active() -> bool:
    if not REQUIRE_D4_SESSION:
        return True
    with _lock:
        if not _d4_session.get("open"):
            return False
        until = float(_d4_session.get("until") or 0)
        if until > 0 and _now() > until:
            _d4_session["open"] = False
            return False
        return True


def set_d4_session(*, open_session: bool, ttl: int | None = None) -> dict[str, Any]:
    """Operator dual-control: open/close D4 session window."""
    with _lock:
        if open_session:
            ttl_v = int(ttl if ttl is not None else D4_SESSION_DEFAULT_TTL)
            until = _now() + ttl_v if ttl_v > 0 else 0.0
            _d4_session["open"] = True
            _d4_session["until"] = until
        else:
            _d4_session["open"] = False
            _d4_session["until"] = 0.0
        snap = dict(_d4_session)
    _receipt("d4_session", {"open": snap["open"], "until": snap["until"]})
    return {
        "ok": True,
        "code": "D4_SESSION",
        "data": {
            "open": snap["open"],
            "until": snap["until"],
            "ttl_default": D4_SESSION_DEFAULT_TTL,
            "required": REQUIRE_D4_SESSION,
        },
    }


def _arm_active() -> bool:
    with _lock:
        if not _arm.get("armed"):
            return False
        until = float(_arm.get("until") or 0)
        if until <= 0 or _now() > until:
            _arm["armed"] = False
            _arm["until"] = 0.0
            return False
        return True


def _set_arm(armed: bool, ttl: int | None = None) -> dict[str, Any]:
    ttl = ARM_TTL_SEC if ttl is None else _clamp_arm_ttl(ttl)
    with _lock:
        if armed:
            token = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
            until = _now() + ttl
            _arm.update({"armed": True, "until": until, "token": token})
        else:
            _arm.update({"armed": False, "until": 0.0, "token": ""})
        snap = dict(_arm)
    _receipt(
        "arm",
        {
            "armed": snap["armed"],
            "until": snap["until"],
            "mode": "toggle" if not snap["until"] else "timed",
        },
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
            until = float(arm.get("until") or 0)
            _arm.update(
                {
                    # Legacy never-expiring arm (until=0) is not honoured.
                    "armed": bool(arm.get("armed")) and until > 0,
                    "until": until,
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
    if not name or _app_denied(name):
        return False
    return INPUT_SCOPE == "operator-proxy" or name in APP_ALLOWLIST


def _require_frontmost_allowed() -> dict[str, Any] | None:
    fm = observe.frontmost_app()
    if not fm.get("ok"):
        return {
            "ok": False,
            "code": "FRONTMOST_FAIL",
            "detail": fm.get("detail"),
            "hint": "Accessibility required",
        }
    app = (fm.get("data") or {}).get("app") or ""
    if _app_denied(app):
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


def _purge_expired_pending() -> None:
    now = _now()
    with _lock:
        dead = [i for i, p in _pending.items() if now - float(p.get("created") or 0) > CONFIRM_TTL_SEC]
        for i in dead:
            _pending.pop(i, None)


def _queue_confirm(action: str, payload: dict[str, Any], summary: str, tier: int = 4) -> dict[str, Any]:
    _purge_expired_pending()
    cid = str(uuid.uuid4())
    entry = {
        "id": cid,
        "action": action,
        "payload": dict(payload),
        "summary": summary[:500],
        "tier": tier,
        "created": _now(),
        "expires": _now() + CONFIRM_TTL_SEC,
    }
    with _lock:
        _pending[cid] = entry
    _receipt("confirm_required", {"id": cid, "action": action, "summary": summary[:200]})
    return {
        "ok": False,
        "code": "CONFIRM_REQUIRED",
        "detail": f"D4 high-blast: confirm within {CONFIRM_TTL_SEC}s",
        "id": cid,
        "data": {
            "confirm_id": cid,
            "summary": summary,
            "action": action,
            "expires_in_sec": CONFIRM_TTL_SEC,
            "how": "python3 bridge/client.py confirm --id %s --yes" % cid,
        },
    }


def _is_high_blast(action: str, payload: dict[str, Any]) -> tuple[bool, str]:
    if action == "desktop.quit":
        app = str(payload.get("app") or "")
        return True, f"QUIT application {app!r}"
    if action == "desktop.press":
        key = str(payload.get("key") or "").strip().lower()
        if key.split("+")[-1] in HIGH_BLAST_KEYS or key in ("cmd+q", "command+q"):
            return True, f"PRESS {key} (may execute focused shell/command)"
    # Optional: type that looks like destructive shell
    if action == "desktop.type":
        t = str(payload.get("text") or "").lower()
        for bad in ("rm -rf", "sudo ", "mkfs", "dd if=", ":(){", "curl | sh", "wget | sh"):
            if bad in t:
                return True, f"TYPE matches high-risk pattern {bad!r}"
    return False, ""


def status_payload() -> dict[str, Any]:
    _purge_expired_pending()
    with _lock:
        arm = dict(_arm)
        pending = [
            {
                "id": p["id"],
                "action": p["action"],
                "summary": p["summary"],
                "expires_in": max(0, int(p["expires"] - _now())),
            }
            for p in _pending.values()
        ]
    return {
        "ok": True,
        "bridge": "up",
        "service": "desktop-leash",
        "version": VERSION,
        "phase": PHASE,
        "phase_name": "layout-control",
        "profile": PROFILE,
        "armed": _arm_active(),
        "arm_until": arm.get("until"),
        "arm_mode": f"timed_{ARM_TTL_SEC}s",
        "require_d4_confirm": REQUIRE_D4_CONFIRM,
        "require_d4_session": REQUIRE_D4_SESSION,
        "d4_session": {
            "open": _d4_session_active(),
            "until": float(_d4_session.get("until") or 0),
            "default_ttl": D4_SESSION_DEFAULT_TTL,
        },
        "pending_confirms": pending,
        "allowed_actions": sorted(ALLOWED_ACTIONS),
        "action_tiers": dict(ACTION_TIERS),
        "input_scope": INPUT_SCOPE,
        "input_policy_current": _input_policy_current(),
        "input_policy_sha256": INPUT_POLICY_SHA,
        "app_allowlist": sorted(APP_ALLOWLIST),
        "app_denylist": sorted(APP_DENYLIST),
        "velocity": {"max": VEL_MAX, "window_sec": VEL_WINDOW},
        "permission_doc": "docs/PERMISSION_TIERS.md",
        "plan": str(Path.home() / "ops/DESKTOP_LEASH_PLAN.md"),
        "note": "Phase 7 layout: desktop.layout + click_window (window-local coords). Never guess full-screen clicks.",
        "integration_doc": "docs/INTEGRATION.md",
        "anti_patterns_doc": "docs/ANTI_PATTERNS.md",
    }


def _execute(action: str, payload: dict[str, Any], job_id: str) -> dict[str, Any]:
    """Run action body after gates passed (and optional confirm)."""
    if ACTION_TIERS.get(action, 0) >= 2 and not _input_policy_current():
        return {"ok": False, "code": "INPUT_POLICY_CHANGED"}
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
    elif action == "desktop.ax":
        res = observe.ax_snapshot(max_elements=int(payload.get("max") or 40))
    elif action == "desktop.region_screenshot":
        CAPTURES.mkdir(parents=True, exist_ok=True)
        out = payload.get("path") or str(
            CAPTURES / f"region-{time.strftime('%Y%m%d-%H%M%S')}-{job_id[:8]}.png"
        )
        res = observe_cua.region_screenshot(
            Path(out),
            int(payload.get("x") or 0),
            int(payload.get("y") or 0),
            int(payload.get("w") or 200),
            int(payload.get("h") or 200),
        )
    elif action == "desktop.ax_click":
        gate = _require_frontmost_allowed()
        if gate:
            res = gate
        else:
            res = observe_cua.ax_click(
                role=str(payload.get("role") or ""),
                title=str(payload.get("title") or ""),
                description=str(payload.get("description") or ""),
                index=int(payload.get("index") or 1),
            )
    elif action == "desktop.layout":
        out = payload.get("path") or ""
        if out:
            res = layout.layout_snapshot(Path(out))
        else:
            res = layout.layout_snapshot(None)
    elif action == "desktop.screenshot_window":
        CAPTURES.mkdir(parents=True, exist_ok=True)
        out = payload.get("path") or str(
            CAPTURES / f"win-{time.strftime('%Y%m%d-%H%M%S')}-{job_id[:8]}.png"
        )
        res = layout.screenshot_window(
            str(payload.get("app") or ""),
            Path(out),
            title_contains=str(payload.get("title") or ""),
        )
    elif action == "desktop.click_window":
        # Focus target first (do not gate on previous frontmost — that was the split-desktop bug)
        app = str(payload.get("app") or "").strip()
        if not app:
            res = {"ok": False, "code": "APP_REQUIRED", "detail": "app required for click_window"}
        elif _app_denied(app):
            res = {"ok": False, "code": "APP_DENIED", "detail": f"{app!r} denylisted"}
        elif not _app_allowed(app):
            res = {
                "ok": False,
                "code": "APP_NOT_ALLOWLISTED",
                "detail": f"cannot click in {app!r}",
                "data": {"allowlist": sorted(APP_ALLOWLIST)},
            }
        else:
            if payload.get("focus", True):
                fr = observe.focus_app(app)
                if not fr.get("ok"):
                    res = fr
                else:
                    time.sleep(0.15)
                    resolved = layout.resolve_click_point(
                        app=app,
                        rel_x=payload.get("rel_x"),
                        rel_y=payload.get("rel_y"),
                        local_x=payload.get("local_x"),
                        local_y=payload.get("local_y"),
                        title_contains=str(payload.get("title") or ""),
                    )
                    if not resolved.get("ok"):
                        res = resolved
                    else:
                        d = resolved["data"]
                        click = proxy_input.click_xy(int(d["global_x"]), int(d["global_y"]))
                        if click.get("ok"):
                            click["data"] = {**(click.get("data") or {}), "resolved": d}
                        res = click
            else:
                resolved = layout.resolve_click_point(
                    app=app,
                    rel_x=payload.get("rel_x"),
                    rel_y=payload.get("rel_y"),
                    local_x=payload.get("local_x"),
                    local_y=payload.get("local_y"),
                    title_contains=str(payload.get("title") or ""),
                )
                if not resolved.get("ok"):
                    res = resolved
                else:
                    d = resolved["data"]
                    click = proxy_input.click_xy(int(d["global_x"]), int(d["global_y"]))
                    if click.get("ok"):
                        click["data"] = {**(click.get("data") or {}), "resolved": d}
                    res = click
    elif action == "desktop.cua_observe":
        res = observe_cua.cua_observe_bundle(
            Path(payload["out_dir"]) if payload.get("out_dir") else None
        )
    elif action == "desktop.focus":
        app = str(payload.get("app") or "").strip()
        if _app_denied(app):
            res = {"ok": False, "code": "APP_DENIED", "detail": f"{app!r} denylisted"}
        elif not _app_allowed(app):
            res = {
                "ok": False,
                "code": "APP_NOT_ALLOWLISTED",
                "detail": f"cannot focus {app!r}",
                "data": {"allowlist": sorted(APP_ALLOWLIST)},
            }
        else:
            res = observe.focus_app(app)
    elif action == "desktop.click":
        gate = _require_frontmost_allowed()
        res = gate if gate else proxy_input.click_xy(int(payload.get("x") or 0), int(payload.get("y") or 0))
    elif action == "desktop.type":
        gate = _require_frontmost_allowed()
        res = gate if gate else observe.type_text(str(payload.get("text") or ""))
    elif action == "desktop.press":
        gate = _require_frontmost_allowed()
        if gate:
            res = gate
        else:
            key = str(payload.get("key") or "return")
            res = proxy_input.press_key(key)
            if res.get("ok") and key.lower().split("+")[-1] in HIGH_BLAST_KEYS:
                res["warning"] = "Return/Enter may execute focused shell command"
    elif action == "desktop.scroll":
        gate = _require_frontmost_allowed()
        res = gate if gate else proxy_input.scroll_dy(int(payload.get("dy") or 0))
    elif action == "desktop.quit":
        app = str(payload.get("app") or "").strip()
        if _app_denied(app) or app in QUIT_DENY:
            res = {"ok": False, "code": "APP_DENIED", "detail": f"cannot quit {app!r}"}
        elif not _app_allowed(app):
            res = {
                "ok": False,
                "code": "APP_NOT_ALLOWLISTED",
                "detail": f"cannot quit {app!r}",
            }
        else:
            res = observe.quit_app(app)
    else:
        res = {"ok": False, "code": "UNKNOWN_ACTION", "detail": action}
    return res


def run_action(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "").strip()
    if action in ("", "status"):
        return status_payload()

    # Confirm resolution is a separate path
    if action == "desktop.confirm":
        return {"ok": False, "code": "USE_CONFIRM_ENDPOINT", "detail": "POST /v1/confirm"}

    if action not in ALLOWED_ACTIONS:
        _receipt("deny", {"action": action, "reason": "UNKNOWN_OR_LOCKED"})
        return {
            "ok": False,
            "code": "UNKNOWN_ACTION",
            "detail": f"unknown or locked action {action!r}",
        }

    if not _arm_active():
        _receipt("deny", {"action": action, "reason": "NOT_ARMED"})
        return {
            "ok": False,
            "code": "NOT_ARMED",
            "detail": "desktop-leash must be ARMED before D1+ actions",
        }

    tier = ACTION_TIERS.get(action, 9)
    # Escalate press return/enter to tier 4
    high, summary = _is_high_blast(action, payload)
    if high:
        tier = 4

    job_id = str(uuid.uuid4())
    _receipt("enqueue", {"id": job_id, "action": action, "tier": tier, "high_blast": high})

    if tier >= 3:
        ok_v, msg_v = _velocity_ok("input")
        if not ok_v:
            _receipt("deny", {"action": action, "reason": "VELOCITY", "detail": msg_v})
            return {"ok": False, "code": "VELOCITY", "detail": msg_v, "id": job_id}

    # D4 dual-control: session must be open before confirm queue / execute
    if high and not _d4_session_active():
        _receipt("deny", {"action": action, "reason": "D4_SESSION_CLOSED"})
        return {
            "ok": False,
            "code": "D4_SESSION_CLOSED",
            "detail": "open D4 dual-control session first: client.py d4-session --open [--ttl 300]",
            "id": job_id,
            "tier": tier,
        }

    # D4: require confirm unless already approved via token
    confirm_id = str(payload.get("confirm_id") or payload.get("confirmed_id") or "")
    if high and REQUIRE_D4_CONFIRM:
        if not confirm_id:
            return _queue_confirm(action, payload, summary or action, tier=4)
        with _lock:
            pend = _pending.get(confirm_id)
        if not pend:
            return {
                "ok": False,
                "code": "CONFIRM_UNKNOWN",
                "detail": f"no pending confirm {confirm_id!r} (expired or wrong id)",
            }
        if (pend.get("action") != action or
                _now() > float(pend.get("expires") or 0) or
                {k:v for k,v in payload.items() if k not in ("confirm_id","confirmed_id")} != pend.get("payload")):
            return {
                "ok": False,
                "code": "CONFIRM_MISMATCH",
                "detail": "confirm_id action mismatch",
            }
        # consume and execute
        with _lock:
            _pending.pop(confirm_id, None)
        _receipt("confirm_consumed", {"id": confirm_id, "action": action})

    res = _execute(action, payload, job_id)
    res = {**res, "id": job_id, "action": action, "tier": tier}
    _receipt("result", {"id": job_id, "action": action, "ok": res.get("ok"), "code": res.get("code")})
    return res


def resolve_confirm(body: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/confirm {id, ok: true|false} — on yes, execute pending action."""
    _purge = _now()
    cid = str(body.get("id") or body.get("confirm_id") or "").strip()
    approved = bool(body.get("ok") or body.get("yes") or body.get("approve"))
    if body.get("ok") is False or body.get("yes") is False or body.get("approve") is False:
        approved = False
    if body.get("no") is True:
        approved = False

    if not cid:
        return {"ok": False, "code": "MISSING_ID", "detail": "confirm id required"}

    with _lock:
        pend = _pending.get(cid)
        if pend and _purge - float(pend.get("created") or 0) > CONFIRM_TTL_SEC:
            _pending.pop(cid, None)
            pend = None

    if not pend:
        return {"ok": False, "code": "CONFIRM_UNKNOWN", "detail": "expired or unknown confirm id"}

    if not approved:
        with _lock:
            _pending.pop(cid, None)
        _receipt("confirm_rejected", {"id": cid, "action": pend["action"]})
        return {
            "ok": True,
            "code": "CONFIRM_REJECTED",
            "detail": "operator rejected high-blast action",
            "data": {"id": cid, "action": pend["action"]},
        }

    if not _arm_active():
        return {"ok": False, "code": "NOT_ARMED", "detail": "re-arm before confirming"}

    if not _d4_session_active():
        return {"ok": False, "code": "D4_SESSION_CLOSED"}

    # Execute only the stored operator-reviewed action.
    with _lock:
        _pending.pop(cid, None)
    action = pend["action"]
    payload = dict(pend.get("payload") or {})
    job_id = str(uuid.uuid4())
    _receipt("confirm_approved", {"id": cid, "action": action, "job": job_id})
    res = _execute(action, payload, job_id)
    res = {
        **res,
        "id": job_id,
        "action": action,
        "confirm_id": cid,
        "tier": 4,
    }
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
        if path == "/v1/confirm":
            self._json(200, resolve_confirm(body))
            return
        if path == "/v1/d4-session":
            open_session = bool(body.get("open") or body.get("armed") or body.get("yes"))
            if body.get("open") is False or body.get("close") is True:
                open_session = False
            ttl = body.get("ttl")
            ttl_i = int(ttl) if ttl is not None else None
            self._json(200, set_d4_session(open_session=open_session, ttl=ttl_i))
            return
        self._json(404, {"ok": False, "code": "NOT_FOUND"})


def main() -> None:
    os.umask(0o077)
    import desktop_gateway
    desktop_gateway.install(globals(), ROOT / 'profiles' / 'desktop_auth.json', [Path('/Users/llm01/agent-control/FREEZE'),Path('/Users/llm01/mcp-assure/FREEZE'),Path('/Users/llm01/Documents/Codex/2026-09-06/plugin-creator-users-llm01-codex-skills-2/outputs/control-plane-access-20260908/project-state/FREEZE')])
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"desktop-leash phase {PHASE} on http://{HOST}:{PORT}", flush=True)
    print(
        f"version={VERSION} d4_confirm={REQUIRE_D4_CONFIRM} "
        f"d4_session_required={REQUIRE_D4_SESSION} "
        f"arm_mode=timed_{ARM_TTL_SEC}s",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", flush=True)


if __name__ == "__main__":
    main()
