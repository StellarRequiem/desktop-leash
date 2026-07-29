#!/usr/bin/env python3
"""CLI client for desktop-leash Phase 1."""

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
        description="Phase 1 observe-only desktop control plane (arm-gated).",
    )
    p.add_argument("--base", default=DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="D0 — bridge health (no arm)")
    sub.add_parser("arm", help="sticky ARM on")
    sub.add_parser("disarm", help="DISARM off")
    sub.add_parser("apps", help="D1 — list foreground apps")
    sub.add_parser("windows", help="D1 — list windows")
    sub.add_parser("displays", help="D1 — display info")
    sc = sub.add_parser("screenshot", help="D1 — full display PNG")
    sc.add_argument("--out", default="", help="output path (default captures/)")
    # Explicit refuses for agent clarity
    sub.add_parser("click", help="Phase 2+ (locked)")
    sub.add_parser("type", help="Phase 2+ (locked)")

    args = p.parse_args(argv)
    base = args.base

    if args.cmd == "status":
        print(json.dumps(call(base, "/v1/status"), indent=2))
        return 0
    if args.cmd == "arm":
        print(json.dumps(call(base, "/v1/arm", {"armed": True, "ttl": 0}), indent=2))
        return 0
    if args.cmd == "disarm":
        print(json.dumps(call(base, "/v1/arm", {"armed": False}), indent=2))
        return 0
    if args.cmd == "apps":
        print(json.dumps(call(base, "/v1/action", {"action": "desktop.apps"}), indent=2))
        return 0
    if args.cmd == "windows":
        print(json.dumps(call(base, "/v1/action", {"action": "desktop.windows"}), indent=2)[:12000])
        return 0
    if args.cmd == "displays":
        print(json.dumps(call(base, "/v1/action", {"action": "desktop.displays"}), indent=2))
        return 0
    if args.cmd == "screenshot":
        body: dict = {"action": "desktop.screenshot"}
        if args.out:
            body["path"] = args.out
        print(json.dumps(call(base, "/v1/action", body), indent=2))
        return 0
    if args.cmd in ("click", "type"):
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": "PHASE1_LOCKED",
                    "detail": f"{args.cmd} is Phase 2+ — observe-only now",
                },
                indent=2,
            )
        )
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
