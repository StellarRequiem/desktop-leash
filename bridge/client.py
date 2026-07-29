#!/usr/bin/env python3
"""CLI client for desktop-leash Phase 4."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT = "http://127.0.0.1:8757"


def call(base: str, path: str, body: dict | None = None) -> dict:
    url = base.rstrip("/") + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="GET" if body is None else "POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"ok": False, "code": "BRIDGE_DOWN", "detail": str(e)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="desktop-leash",
        description="Phase 4 desktop control plane: observe + allowlisted input + D4 confirm.",
    )
    p.add_argument("--base", default=DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    sub.add_parser("arm")
    sub.add_parser("disarm")
    sub.add_parser("apps")
    sub.add_parser("windows")
    sub.add_parser("displays")
    sub.add_parser("frontmost")
    sc = sub.add_parser("screenshot")
    sc.add_argument("--out", default="")
    fo = sub.add_parser("focus")
    fo.add_argument("--app", required=True)
    cl = sub.add_parser("click")
    cl.add_argument("--x", type=int, required=True)
    cl.add_argument("--y", type=int, required=True)
    ty = sub.add_parser("type")
    ty.add_argument("--text", required=True)
    pr = sub.add_parser("press")
    pr.add_argument("--key", default="return")
    scrl = sub.add_parser("scroll")
    scrl.add_argument("--dy", type=int, default=400)
    qt = sub.add_parser("quit", help="D4 — quit allowlisted app (needs confirm)")
    qt.add_argument("--app", required=True)
    cf = sub.add_parser("confirm", help="approve/reject pending D4 action")
    cf.add_argument("--id", required=True, help="confirm_id from CONFIRM_REQUIRED")
    g = cf.add_mutually_exclusive_group(required=True)
    g.add_argument("--yes", action="store_true")
    g.add_argument("--no", action="store_true")
    sub.add_parser("pending", help="list pending D4 confirms")
    ax = sub.add_parser("ax", help="Phase 5 AX snapshot (frontmost window UI tree)")
    ax.add_argument("--max", type=int, default=40)
    d4s = sub.add_parser("d4-session", help="Phase 5 dual-control window for D4")
    d4s.add_argument("--open", action="store_true")
    d4s.add_argument("--close", action="store_true")
    d4s.add_argument("--ttl", type=int, default=300)

    args = p.parse_args(argv)
    base = args.base

    def out(d: dict) -> int:
        print(json.dumps(d, indent=2)[:16000])
        return 0 if d.get("ok") or d.get("code") == "CONFIRM_REQUIRED" else 1

    if args.cmd == "status":
        return out(call(base, "/v1/status"))
    if args.cmd == "arm":
        return out(call(base, "/v1/arm", {"armed": True, "ttl": 0}))
    if args.cmd == "disarm":
        return out(call(base, "/v1/arm", {"armed": False}))
    if args.cmd == "apps":
        return out(call(base, "/v1/action", {"action": "desktop.apps"}))
    if args.cmd == "windows":
        return out(call(base, "/v1/action", {"action": "desktop.windows"}))
    if args.cmd == "displays":
        return out(call(base, "/v1/action", {"action": "desktop.displays"}))
    if args.cmd == "frontmost":
        return out(call(base, "/v1/action", {"action": "desktop.frontmost"}))
    if args.cmd == "screenshot":
        body: dict = {"action": "desktop.screenshot"}
        if args.out:
            body["path"] = args.out
        return out(call(base, "/v1/action", body))
    if args.cmd == "focus":
        return out(call(base, "/v1/action", {"action": "desktop.focus", "app": args.app}))
    if args.cmd == "click":
        return out(
            call(base, "/v1/action", {"action": "desktop.click", "x": args.x, "y": args.y})
        )
    if args.cmd == "type":
        return out(call(base, "/v1/action", {"action": "desktop.type", "text": args.text}))
    if args.cmd == "press":
        return out(call(base, "/v1/action", {"action": "desktop.press", "key": args.key}))
    if args.cmd == "scroll":
        return out(call(base, "/v1/action", {"action": "desktop.scroll", "dy": args.dy}))
    if args.cmd == "quit":
        return out(call(base, "/v1/action", {"action": "desktop.quit", "app": args.app}))
    if args.cmd == "pending":
        st = call(base, "/v1/status")
        pend = st.get("pending_confirms") or []
        print(json.dumps({"ok": True, "pending_confirms": pend}, indent=2))
        return 0
    if args.cmd == "confirm":
        return out(
            call(
                base,
                "/v1/confirm",
                {"id": args.id, "ok": bool(args.yes), "no": bool(args.no)},
            )
        )
    if args.cmd == "ax":
        return out(
            call(base, "/v1/action", {"action": "desktop.ax", "max": args.max})
        )
    if args.cmd == "d4-session":
        if args.close:
            return out(call(base, "/v1/d4-session", {"open": False}))
        if args.open:
            return out(call(base, "/v1/d4-session", {"open": True, "ttl": args.ttl}))
        st = call(base, "/v1/status")
        print(json.dumps({"ok": True, "d4_session": st.get("d4_session"), "require_d4_session": st.get("require_d4_session")}, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
