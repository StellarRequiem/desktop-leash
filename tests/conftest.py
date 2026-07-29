"""Import the desktop bridge and fully isolate every test from live state.

A real desktop bridge runs on 8757 against the same receipts/state files, and
the bridge can drive the actual desktop. This fixture redirects receipts/state
to a temp dir, resets all in-memory gate state, and stubs the one function that
reads the live OS (observe.frontmost_app), so the suite can never arm, open a
dual-control session, or touch the desktop.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "bridge"
for p in (str(ROOT), str(BRIDGE)):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def isolate_bridge(tmp_path, monkeypatch):
    import observe
    import server

    monkeypatch.setattr(server, "RECEIPTS", tmp_path / "receipts")
    monkeypatch.setattr(server, "STATE_PATH", tmp_path / ".state.json")
    # never read the real desktop; default to a denied frontmost
    monkeypatch.setattr(observe, "frontmost_app", lambda: {"ok": True, "data": {"app": "Terminal"}})
    # reset all gate state
    server._arm.update({"armed": False, "until": 0.0, "token": ""})
    server._d4_session.update({"open": False, "until": 0.0})
    server._vel.clear()
    server._pending.clear()
    yield
