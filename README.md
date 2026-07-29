# desktop-leash

**Phase 5 — AX snapshot + D4 dual-control** full-computer-use control plane for macOS.

Sibling to [browser-leash](../browser-leash) (Chrome only). Same philosophy: **authority is not ambient**.

```
  Grok / CLI  ──HTTP 127.0.0.1:8757──►  desktop-leash bridge
                                              │
                                              ├── screencapture (Screen Recording)
                                              ├── osascript apps/windows (Accessibility)
                                              └── receipts/*.jsonl
```

Plan: `~/ops/DESKTOP_LEASH_PLAN.md`

## Phase 5 scope

| Can | Cannot |
|-----|--------|
| status (no arm) | non-allowlisted apps |
| arm / disarm (sticky toggle) | password managers / Mail / Messages |
| list apps / windows / displays / frontmost | remote access |
| screenshot | ambient always-on |
| focus allowlisted app | quit Finder / system apps |
| click / type / press / scroll if frontmost allowlisted | auto-approve D4 |
| D4: quit / Return after **d4-session --open** + **confirm --yes** | |
| AX snapshot (redacted front window) | |

## Quick start

```bash
# Terminal 1
python3 ~/desktop-leash/bridge/server.py

# Terminal 2
python3 ~/desktop-leash/bridge/client.py status
python3 ~/desktop-leash/bridge/client.py arm      # sticky ON
python3 ~/desktop-leash/bridge/client.py apps
python3 ~/desktop-leash/bridge/client.py windows
python3 ~/desktop-leash/bridge/client.py screenshot --out /tmp/desk.png
python3 ~/desktop-leash/bridge/client.py focus --app TextEdit
python3 ~/desktop-leash/bridge/client.py type --text "hello from desktop-leash"
# D4 — needs confirm
python3 ~/desktop-leash/bridge/client.py press --key return
# → CONFIRM_REQUIRED + confirm_id
python3 ~/desktop-leash/bridge/client.py confirm --id <id> --yes   # or --no
python3 ~/desktop-leash/bridge/client.py disarm   # when done
```

## Permissions (operator, once)

See **`docs/LOAD.md`**.

1. **Screen Recording** — required for `screenshot`  
2. **Accessibility** — required for full `apps` / `windows` lists  

Grant to the app that runs the bridge (Terminal, Ghostty, or `python` as shown by the OS).

## Docs

- `docs/INTEGRATION.md` — which plane when
- `docs/ANTI_PATTERNS.md` — never-do list
- `docs/LOAD.md` — macOS permissions
- `docs/POSTABLE_EXPLAINER.md` — claim-safe public copy
- `docs/CLAIMS.md` — claim cards, hard refuses, hold-test log
- `docs/OPEN_SOURCE_READINESS.md` — public prep (decision deferred)

## Safety

- Loopback only (`127.0.0.1`)
- Deny-by-default actions
- Sticky ARM until DISARM
- Receipts under `receipts/` (gitignored)
- Screenshots under `captures/` (gitignored; may contain PII — local only)

## Version

**0.5.0** — Phase 5 AX + D4 dual-control session.
