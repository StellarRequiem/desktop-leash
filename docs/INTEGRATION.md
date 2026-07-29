# Integration — which control plane when

For Grok Build and operators. **Wrong plane = wrong risk.**

```
Grok Build
  ├── shell / files / git / tests     → always prefer for code
  ├── agent-control (preferred for plane tools)
  │     └── mcp-assure AdaptiveGate → browser.* / desktop.* / plane.*
  ├── browser-leash :8756             → Chrome session (direct debug OK)
  ├── desktop-leash :8757             → other GUI (direct debug OK)
  └── mcp-assure                      → package / packs / purple
```

Preferred agent path for browser/desktop: **`python3 ~/agent-control/cli.py call …`**  
(see `~/agent-control/ARCHITECTURE.md`).

## Decision table

| Task | Plane | Notes |
|------|--------|------|
| Edit files, pytest, git, pip | **Shell tools** | Fastest; clearest receipts |
| Open X, GitHub.com, xclusivexo, PyPI in **Chrome** | **browser-leash** | Host allowlist + sticky ARM + post confirm |
| List apps / windows / screenshot whole desktop | **desktop-leash** | Phase 1+ observe |
| Type into TextEdit / Notes / Terminal GUI | **desktop-leash** | Allowlist + frontmost gate |
| Click UI outside Chrome | **desktop-leash** | Coords; AX later |
| Quit app | **desktop-leash D4** | `CONFIRM_REQUIRED` → operator `--yes` |
| Press Return in Terminal (may run command) | **desktop-leash D4** | Confirm required |
| MCP tool call policy | **mcp-assure** | AdaptiveGate / packs |
| Numeric / accuracy public claims | **verity + claim-gate** | Not a leash |

## Boot both leashes (typical session)

```bash
# Chrome
nohup python3 ~/browser-leash/bridge/server.py >>~/browser-leash/receipts/bridge.log 2>&1 &
# Desktop
nohup python3 ~/desktop-leash/bridge/server.py >>~/desktop-leash/receipts/bridge.log 2>&1 &

python3 ~/browser-leash/bridge/client.py status   # ARM via Chrome popup
python3 ~/desktop-leash/bridge/client.py arm      # sticky CLI arm
```

## Agent SOP

1. Prefer shell over desktop typing for code/commands.  
2. Prefer browser-leash over desktop for anything in Chrome.  
3. Never auto-approve D4 / X post without operator.  
4. If `NOT_ARMED`: ask operator to arm the right plane.  
5. If `APP_NOT_ALLOWLISTED` / `HOST_DENIED`: do not invent bypass — propose allowlist change.  

## Version map

| Plane | Port | Phase (as of 2026-07-29) |
|-------|------|---------------------------|
| browser-leash | 8756 | Chrome control + sticky ARM |
| desktop-leash | 8757 | Phase 4 integration |
| mcp-assure | n/a (library/CLI) | 0.3.x public |
