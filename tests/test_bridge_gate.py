"""Re-runnable proof for the desktop-leash gate.

desktop-leash can focus apps, click, type, press keys, and quit apps. The public
claims are "ARM required, credential managers denied, high-blast actions need a
dual-control (D4) session + explicit confirm." These tests are the evidence:

  - credential/secret apps are denylisted (1Password, Keychain, wallets, MFA);
  - unknown actions and disarmed requests never proceed;
  - quit / return-press are classified high-blast and cannot execute without an
    open D4 session AND an explicit confirm — the request stops at CONFIRM_REQUIRED.

None of these paths reach _execute (which would touch the desktop): they assert
the deny/confirm decisions that happen *before* execution. State is reset per
test and observe.frontmost_app is stubbed, so the live bridge is never touched.
"""

from __future__ import annotations

import server


# ---- credential-manager denylist (the core desktop safety) ----------------

def test_password_and_wallet_apps_denied():
    for app in ("1Password", "1Password 7", "Bitwarden", "Keychain Access", "Coinbase", "Ledger Live", "Authy"):
        assert server._app_allowed(app) is False, f"{app} must never be allowlisted"


def test_denylist_beats_allowlist():
    # even if an env/profile tried to allow it, the denylist wins
    assert "1Password" in server.APP_DENYLIST
    assert server._app_allowed("1Password") is False


def test_empty_and_unknown_app_denied():
    assert server._app_allowed("") is False
    assert server._app_allowed("SomeRandomApp") is False


def test_an_allowlisted_app_is_allowed():
    allowed = server.APP_ALLOWLIST - server.APP_DENYLIST
    assert allowed, "allowlist should be non-empty"
    assert server._app_allowed(next(iter(allowed))) is True


# ---- high-blast classification --------------------------------------------

def test_quit_is_high_blast():
    high, _ = server._is_high_blast("desktop.quit", {"app": "TextEdit"})
    assert high is True


def test_return_press_is_high_blast():
    for key in ("return", "enter"):
        high, _ = server._is_high_blast("desktop.press", {"key": key})
        assert high is True, f"press {key} should be high-blast"


def test_destructive_type_is_high_blast():
    high, _ = server._is_high_blast("desktop.type", {"text": "sudo rm -rf /"})
    assert high is True


def test_benign_action_not_high_blast():
    assert server._is_high_blast("desktop.screenshot", {})[0] is False
    assert server._is_high_blast("desktop.type", {"text": "hello world"})[0] is False


# ---- run_action gate: unknown + disarmed ----------------------------------

def test_unknown_action_denied():
    out = server.run_action({"action": "desktop.shell", "cmd": "id"})
    assert out["ok"] is False and out["code"] == "UNKNOWN_ACTION"


def test_valid_action_denied_when_disarmed():
    out = server.run_action({"action": "desktop.screenshot"})
    assert out["ok"] is False and out["code"] == "NOT_ARMED"


# ---- high-blast dual-control: quit cannot execute unattended --------------

def test_quit_blocked_without_d4_session():
    server._set_arm(True, ttl=0)  # armed, but no D4 session
    out = server.run_action({"action": "desktop.quit", "app": "TextEdit"})
    assert out["ok"] is False and out["code"] == "D4_SESSION_CLOSED"


def test_quit_requires_confirm_even_with_d4_open():
    server._set_arm(True, ttl=0)
    server.set_d4_session(open_session=True, ttl=0)
    out = server.run_action({"action": "desktop.quit", "app": "TextEdit"})
    # armed + session open, but no confirm_id -> stops at confirm, never executes
    assert out["ok"] is False and out["code"] == "CONFIRM_REQUIRED"
    assert out["data"]["confirm_id"]


def test_bad_confirm_id_does_not_execute():
    server._set_arm(True, ttl=0)
    server.set_d4_session(open_session=True, ttl=0)
    out = server.run_action({"action": "desktop.quit", "app": "TextEdit", "confirm_id": "nope"})
    assert out["ok"] is False and out["code"] == "CONFIRM_UNKNOWN"


# ---- arm + D4 state machines ----------------------------------------------

def test_arm_then_disarm():
    server._set_arm(True, ttl=0)
    assert server._arm_active() is True
    server._set_arm(False)
    assert server._arm_active() is False


def test_d4_session_open_close():
    server.set_d4_session(open_session=True, ttl=0)
    assert server._d4_session_active() is True
    server.set_d4_session(open_session=False)
    assert server._d4_session_active() is False
