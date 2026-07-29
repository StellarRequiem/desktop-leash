#!/usr/bin/env python3
"""CLI client for desktop-leash Phase 2."""

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
        description="Phase 2 desktop control plane: observe + allowlisted input.",
    )
    p.add_argument("--base", default=DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="D0 — bridge health (no arm)")
    sub.add_parser("arm", help="sticky ARM on")
    sub.add_parser("disarm", help="DISARM off")
    sub.add_parser("apps", help="D1 — list apps")
    sub.add_parser("windows", help="D1 — list windows")
    sub.add_parser("displays", help="D1 — displays")
    sub.add_parser("frontmost", help="D1 — frontmost app")
    sc = sub.add_parser("screenshot", help="D1 — PNG")
    sc.add_argument("--out", default="")

    fo = sub.add_parser("focus", help="D2 — focus allowlisted app")
    fo.add_argument("--app", required=True)

    cl = sub.add_parser("click", help="D3 — click at screen x,y (frontmost must be allowlisted)")
    cl.add_argument("--x", type=int, required=True)
    cl.add_argument("--y", type=int, required=True)

    ty = sub.add_parser("type", help="D3 — type text (no newlines; frontmost allowlisted)")
    ty.add_argument("--text", required=True)

    pr = sub.add_parser("press", help="D3 — key: return|tab|escape|space|arrows|…")
    pr.add_argument("--key", default="return")

    scrl = sub.add_parser("scroll", help="D3 — scroll dy (page keys)")
    scrl.add_argument("--dy", type=int, default=400)

    args = p.parse_args(argv)
    base = args.base

    def out(d: dict) -> int:
        print(json.dumps(d, indent=2)[:16000])
        return 0 if d.get("ok") else 1

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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
