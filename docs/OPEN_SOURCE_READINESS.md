# desktop-leash — public open-source readiness

**Decision status:** **DEFERRED** (local Phase 5 control plane).  
Prep only — no remote push without operator ask.

## What would become public

| Surface | Path |
|---------|------|
| Bridge | `bridge/server.py`, `client.py`, `observe.py` |
| Docs | LOAD, PERMISSION_TIERS, INTEGRATION, ANTI_PATTERNS, CLAIMS |
| Plan | can reference architecture; drop private ops paths |

## Before any public repo

- [ ] Operator explicit “open-source desktop-leash” ask  
- [ ] LICENSE  
- [ ] CLAIMS.md aligned with Phase 5 (AX redacted, D4 dual-control)  
- [ ] THREAT_MODEL (Accessibility + Screen Recording = high trust)  
- [ ] No captures/receipts in tree  
- [ ] Default allow/deny lists documented as starting point  
- [ ] LOAD.md with System Settings paths  
- [ ] Smoke script without personal paths  

## Claim ceiling if public

> Local macOS desktop control plane: arm-gated observe and allowlisted input, AX snapshot (redacted), dual-control session + confirm on high-blast — not unattended OS takeover.

## Phase 5 features to mention honestly

- `desktop.ax` — shallow redacted UI tree  
- `d4-session` — dual-control time window before quit/Return  
- Profiles via agent-control (may stay in agent-control repo)  
