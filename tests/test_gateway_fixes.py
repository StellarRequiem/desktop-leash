"""desktop-leash: multi-client keys, denylist always wins, arming always expires."""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

BRIDGE = Path(__file__).resolve().parents[1] / "bridge"
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(BRIDGE.parent / "scripts"))
import desktop_auth as A  # noqa: E402
import desktop_gateway as G  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

PUB = A.b64(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))


def _priv(p: Path, data: bytes) -> Path:
    p.write_bytes(data); p.chmod(0o600); return p


def _cfg(tmp, clients):
    codex = _priv(tmp / "codex-action-key", os.urandom(32))
    c = {"version": A.VERSION, "client_id": "codex", "client_key_path": str(codex),
         "operator_public_key": PUB, "action_clients": clients}
    return _priv(tmp / "desktop_auth.json", json.dumps(c).encode())


def test_placeholders_ignored_codex_only(tmp_path):
    cfg = _cfg(tmp_path, [{"client_id": "grok", "client_key_path": "/nope", "enabled": False}])
    assert set(A.from_config(str(cfg)).actions) == {"codex"}


def test_enabled_clients_registered_and_sign(tmp_path):
    g = _priv(tmp_path / "plane-grok-action-key", os.urandom(32))
    cl = _priv(tmp_path / "plane-claude-action-key", os.urandom(32))
    cfg = _cfg(tmp_path, [{"client_id": "grok", "client_key_path": str(g), "enabled": True},
                          {"client_id": "claude", "client_key_path": str(cl), "enabled": True},
                          {"client_id": "ollama", "client_key_path": "/x", "enabled": False}])
    auth = A.from_config(str(cfg))
    assert set(auth.actions) == {"codex", "grok", "claude"}
    env = A.action_envelope(g.read_bytes(), auth.epoch, "GET", "/v1/status", {}, "grok")
    assert auth.authorize(env, "GET", "/v1/status", {})["key_id"] == "grok"
    wrong = A.action_envelope(g.read_bytes(), auth.epoch, "GET", "/v1/status", {}, "claude")
    with pytest.raises(A.Refused, match="BAD_SIGNATURE"):
        auth.authorize(wrong, "GET", "/v1/status", {})


def test_enabled_but_missing_key_fails_closed(tmp_path):
    cfg = _cfg(tmp_path, [{"client_id": "grok", "client_key_path": str(tmp_path / "none"), "enabled": True}])
    with pytest.raises(A.Refused, match="ACTION_KEY_MISSING:grok"):
        A.from_config(str(cfg))


def test_shared_or_reused_key_refused(tmp_path):
    cfg = _cfg(tmp_path, [{"client_id": "grok", "client_key_path": str(tmp_path / "codex-action-key"),
                           "enabled": True}])
    with pytest.raises(A.Refused, match="SHARED_CLIENT_KEY"):
        A.from_config(str(cfg))
    data = os.urandom(32)
    a = _priv(tmp_path / "a", data); b = _priv(tmp_path / "b", data)
    cfg = _cfg(tmp_path, [{"client_id": "grok", "client_key_path": str(a), "enabled": True},
                          {"client_id": "claude", "client_key_path": str(b), "enabled": True}])
    with pytest.raises(A.Refused, match="SHARED_CLIENT_KEY"):
        A.from_config(str(cfg))


def test_shipped_profile_is_placeholder_only():
    d = json.loads((BRIDGE.parent / "profiles" / "desktop_auth.json").read_text())
    ids = {c["client_id"]: c for c in d["action_clients"]}
    assert set(ids) == {"grok", "claude", "ollama", "codex-plane"}
    assert not any(c["enabled"] for c in ids.values())
    assert d["client_id"] == "codex"


def test_mint_script(tmp_path):
    import mint_action_key as M
    p = M.mint("grok", tmp_path)
    assert p.stat().st_size == 32 and (p.stat().st_mode & 0o777) == 0o600
    with pytest.raises(FileExistsError):
        M.mint("grok", tmp_path)
    with pytest.raises(SystemExit):
        M.mint("codex", tmp_path)


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.delenv("DESKTOP_LEASH_ARM_TTL", raising=False)
    import types
    for name in ("observe", "observe_cua", "layout", "proxy_input"):
        if importlib.util.find_spec(name) is None:  # macOS-only modules; stub off-Mac
            monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sys.modules.pop("server", None)
    srv = importlib.import_module("server")
    monkeypatch.setattr(srv, "STATE_PATH", tmp_path / "arm.json")
    monkeypatch.setattr(srv, "_receipt", lambda *a, **k: None)
    return srv


def test_denylist_wins_in_operator_proxy(server):
    server.INPUT_SCOPE = "operator-proxy"
    for app in ("1Password", "Mail", "Messages", "Keychain Access", "Wallet"):
        assert server._app_denied(app) and not server._app_allowed(app)
    assert server._app_allowed("ChatGPT")


def test_arm_default_and_clamp(server):
    assert server.ARM_TTL_SEC == 900
    assert server._clamp_arm_ttl(0) == 900
    assert server._clamp_arm_ttl(-5) == 900
    assert server._clamp_arm_ttl("junk") == 900
    assert server._clamp_arm_ttl(10**9) == 86400
    snap = server._set_arm(True, 0)
    assert snap["until"] > 0 and snap["until"] - server._now() <= 900
    server._set_arm(False)


def test_legacy_forever_arm_not_honoured(server):
    server.STATE_PATH.write_text(json.dumps({"arm": {"armed": True, "until": 0, "token": "x"}}))
    server._load_state()
    assert server._arm_active() is False
    with server._lock:
        server._arm.update(armed=True, until=0.0)
    assert server._arm_active() is False


def test_gateway_maps_ttl_zero_to_default(tmp_path, server):
    calls = []
    ns = {"_set_arm": lambda a, t: calls.append(t) or {"armed": a, "until": 1}, "ARM_TTL_SEC": 900,
          "_receipt": lambda *a: None, "set_d4_session": lambda **k: None, "_lock": server._lock,
          "_pending": {}}

    class Auth:
        epoch = "e"
        def authorize(self, *a): return {"role": "operator", "key_id": "operator"}
    c = G.Controller(ns, Auth())
    # Codex's pinned restart path (prove_live) arms with ttl=0; it must succeed but expire.
    assert c.dispatch("POST", "/v1/arm", {"armed": True, "ttl": 0}, {})["armed"] is True
    assert c.dispatch("POST", "/v1/arm", {"armed": True}, {})["ok"]
    assert calls == [900, 900]
    for bad in (-1, 86401, "0", 1.5):
        with pytest.raises(A.Refused, match="ARM_TTL"):
            c.dispatch("POST", "/v1/arm", {"armed": True, "ttl": bad}, {})
