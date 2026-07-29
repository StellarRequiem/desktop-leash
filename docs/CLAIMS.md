# Claim gate — control stack (mcp-assure · browser-leash · desktop-leash)

Public language must stay **≤ evidence**. Pair with:

- `~/mcp-assure/CLAIMS.md` (package-only)
- `/claim-gate` skill
- `docs/POSTABLE_EXPLAINER.md` (draft copy only — not auto-posted)

**Ladder:** Lead → Candidate → Verified → Published (operator OK).

---

## Claim cards

### Claim A — Deny-by-default tool gate (mcp-assure)

| Field | Value |
|-------|--------|
| **State** | **Verified** (public package) · **Published** on GitHub/PyPI/site after operator ship |
| **Evidence** | https://github.com/StellarRequiem/mcp-assure · `pip install mcp-assure` · `mcp-assure check` · CI · `CLAIMS.md` in repo · purple fixtures |
| **Local note** | On this host use `~/mcp-assure/.venv/bin/mcp-assure` or `cd ~/mcp-assure && .venv/bin/python -m mcp_assure` — bare `mcp-assure` may be off PATH (not a product failure) |
| **Caveats** | Runtime tool-call gate only. Not a code vuln scanner. Not a full SOC. Shell tools in Grok are **not** automatically behind this gate unless the host wires `AssuredToolDispatcher` / AdaptiveGate. |
| **Public wording** | “mcp-assure is a plug-in deny-by-default assurance layer for MCP-style tool calls. The model proposes; the gate decides. Not a full SOC.” |

### Claim B — Chrome session control (browser-leash)

| Field | Value |
|-------|--------|
| **State** | **Verified locally** · **not Published** as a public product (local control plane) |
| **Evidence** | Bridge `:8756` · extension **0.3.7** live hello match · sticky ARM · `require_post_confirm` · host allowlist · receipts under `~/browser-leash/receipts/` · operator hold-tests (NOT_ARMED / Post disabled refuse) |
| **Caveats** | Chrome only. Not ambient RPA. Auto-enable of X Post button still limited (React). Draft ≠ publish. Local-only; no public install story yet. |
| **Public wording** | “Local Chrome control plane with sticky arm, host allowlist, and human confirm on publish — not auto-post.” |

### Claim C — Desktop observe + allowlisted input (desktop-leash)

| Field | Value |
|-------|--------|
| **State** | **Verified locally** (Phase 4) · **not Published** as product |
| **Evidence** | Bridge `:8757` · **v0.4.0** · phase=4 · sticky arm · D4 `require_d4_confirm` · hold-tests 2026-07-29: `NOT_ARMED`, `APP_DENIED` (1Password), `CONFIRM_REQUIRED` → `CONFIRM_REJECTED` on Return · skill + INTEGRATION/ANTI_PATTERNS |
| **Caveats** | Allowlisted apps only. Password managers denylisted. Quit/Return need human confirm. Not full human-equivalent CUA. Screenshots may hold PII (local only). |
| **Public wording** | “Local macOS desktop control plane: arm-gated observe and allowlisted input, with human confirm on high-blast actions — not unattended OS takeover.” |

### Claim D — “Three planes, authority is not ambient” (stack narrative)

| Field | Value |
|-------|--------|
| **State** | **Candidate → Verified locally** as *operating practice* · **not** a third-party audited product claim |
| **Evidence** | Live dual bridges; routing docs `INTEGRATION.md`; refuse paths re-run; skill SOPs; operator protocol red lines |
| **Caveats** | Narrative about *how we work*, not a compliance certification. Shell remains high-trust and separate. Grok host wire for all tools is optional proof (`examples/grok_host_wire.py`) — do not claim every Grok tool is gated. |
| **Public wording** | “Split surfaces — shell for code, browser-leash for Chrome, desktop-leash for other GUI, mcp-assure when the host wires it — each with arm/allowlists/receipts where built.” |

---

## What not to claim (hard refuse)

| Overclaim | Why it fails | Closest true wording |
|-----------|--------------|----------------------|
| “Full computer use like a human with no limits” | Allowlist, arm, D4, denylist, no ambient session | “Arm-gated, allowlisted desktop actions with human confirm on high-blast” |
| “Stops all agent attacks / full SOC” | Wrong product class; no SIEM/IR/EDR surface | “Runtime gate for mediated tool calls / local leashes for browser+desktop” |
| “Auto-posts to X without human” | `require_post_confirm`; React Post may stay disabled; operator owns publish | “Draft under leash; publish only after human confirm” |
| “Every Grok tool is gated” | Shell tools bypass mcp-assure unless host wires cannot-bypass dispatcher | “mcp-assure gates calls that route through the assured host path” |
| “We red-teamed the stack” (formal RT) | Operator adversarial **hold-tests**, not third-party red team report | “Operator hold-tests: unarmed / denylist / confirm-reject paths refuse” |
| “Public full CUA product” | browser-leash + desktop-leash are **local**; only mcp-assure is public package | Name the public surface (mcp-assure) separately from local leashes |
| Win-rate / detection-rate % | No holdout study | Forbidden until study exists |
| “Would have stopped [incident] end-to-end” | Different surfaces (data plane, K8s, mesh) | Scope only to mediated tool calls / local session control |

---

## Soft language to avoid in drafts

| Tempting phrase | Prefer |
|-----------------|--------|
| red-teamed | operator hold-test / adversarial check |
| full computer use (unqualified) | phase-N desktop control plane (local) |
| secure agent / unbreakable | deny-by-default + human gates on high-blast |
| we control the Mac | arm-gated allowlisted actions when operator arms |
| production-proven at scale | local verified; public for mcp-assure install path only |

---

## Hold-test log (re-run before any public stack post)

| # | Check | Expected | Last local |
|---|--------|----------|------------|
| 1 | desktop disarm → apps | `NOT_ARMED` | 2026-07-29 OK |
| 2 | focus 1Password | `APP_DENIED` / denylisted | 2026-07-29 OK |
| 3 | press return (allowlisted) | `CONFIRM_REQUIRED` | 2026-07-29 OK |
| 4 | confirm --no | `CONFIRM_REJECTED`, no side effect | 2026-07-29 OK |
| 5 | browser require_post_confirm | true when armed | 2026-07-29 OK (status) |
| 6 | mcp-assure status/check | CLI healthy in venv or after `pip install` | 2026-07-29 venv OK |

Commands:

```bash
# desktop
python3 ~/desktop-leash/bridge/client.py disarm
python3 ~/desktop-leash/bridge/client.py apps   # NOT_ARMED
python3 ~/desktop-leash/bridge/client.py arm
python3 ~/desktop-leash/bridge/client.py focus --app 1Password   # denied
python3 ~/desktop-leash/bridge/client.py focus --app TextEdit
python3 ~/desktop-leash/bridge/client.py press --key return      # confirm required
python3 ~/desktop-leash/bridge/client.py confirm --id <id> --no

# mcp-assure (local venv)
~/mcp-assure/.venv/bin/mcp-assure status
~/mcp-assure/.venv/bin/mcp-assure check
```

---

## Upgrade path (work queue — only if operator prioritizes)

| Gap | Work that upgrades the claim | Still cannot claim after |
|-----|------------------------------|---------------------------|
| Grok shell not gated | Wire cannot-bypass host for chosen tools; re-run `grok_host_wire.py` | “all tools” forever unless every tool routes |
| browser-leash not public | Decide open-source vs private; docs + threat model + claim file | OS-wide CUA |
| desktop-leash not public | Same + LOAD permissions story + smoke script in CI-like form | human-equivalent CUA |
| Post auto-enable | browser-leash fill/Post work; still human confirm | auto-post without human |
| Formal red team | Scoped engagement + report | marketing “unbreakable” |

---

## State summary

| Surface | Public product? | Claim ceiling today |
|---------|-----------------|---------------------|
| mcp-assure | Yes (GitHub/PyPI) | Verified runtime gate language per package `CLAIMS.md` |
| browser-leash | No | Local verified session control |
| desktop-leash | No | Local verified Phase 4 control plane |
| Stack narrative | Ops practice | Candidate–Verified *locally*; publish only with caveats above |
