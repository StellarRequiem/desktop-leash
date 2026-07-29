# Postable explainer — control planes (claim-safe)

Use on X / site only after operator edit. **Facts ≤ evidence.**

---

## Short (X-length ~500–700 chars if Premium; trim as needed)

```
Built a local agent control stack — not “full CUA free-for-all.”

Three planes, same rule: authority is not ambient.

1) mcp-assure — deny-by-default gate for MCP-style tool calls
   (policy · velocity · campaign freeze · receipts · CLI)
2) browser-leash — Chrome only, sticky ARM, host allowlist, human Post confirm
3) desktop-leash — macOS observe + allowlisted click/type, D4 confirm for quit/Return

How work changes:
• Agent can ship + prove on disk/web under gates
• Unarmed / wrong app / disabled Post → refuse (operator hold-tests)
• High-blast needs explicit confirm — not silent execute

pip install mcp-assure && mcp-assure check   # public package
# browser-leash + desktop-leash = local control planes (not a public install yet)

Not a full SOC. Not unattended OS takeover.
```
# Claim cards: docs/CLAIMS.md

---

## Medium (thread / blog blurb)

```
What we built (local, loopback, operator-armed):

mcp-assure (public) — open security CLI + runtime for agent tool calls.
The model proposes; the gate decides. Adaptive campaign scoring can escalate/freeze.
Zero core deps. Re-runnable purple fixtures. Not a hosted vuln scanner
(different job than Codex Security CLI).

browser-leash (local) — Chrome session control for X/GitHub/site.
Sticky ARM toggle. Deny unknown hosts/actions. Draft + human-gated publish
when React won’t enable Post. Operator hold-test: unarmed / disabled-Post refuse.

desktop-leash (local) — Phase 4 path for the rest of the Mac (not a public product):
screenshot, list apps/windows, focus allowlisted apps, click/type/press/scroll.
Quit and Return require confirm --yes. Password managers denylisted.

How this changes work:
Before: agent either stuck in chat or trusted with everything.
Now: split surfaces — shell for code, browser-leash for Chrome, desktop-leash for other GUI —
each with arm, allowlists, receipts, and human gates on high blast.

Session shape today:
1) Operator ARMs the plane they mean (browser and/or desktop).
2) Agent does the work on the right surface — no “just click whatever.”
3) Wrong app / unarmed / disabled Post → hard refuse (operator hold-tests).
4) High-blast (quit, Return, publish) → human confirm, not silent execute.
5) DISARM when the day ends. Authority is not ambient.

That’s how you get leverage without ambient authority.
```

---

## What not to claim

Full claim cards + hold-test log: **`docs/CLAIMS.md`**.

| Do not say | Closest true wording |
|------------|----------------------|
| Full computer use like a human with no limits | Arm-gated, allowlisted desktop actions + human confirm on high-blast |
| Stops all agent attacks / full SOC | Runtime gate for mediated tool calls; local leashes for browser/desktop |
| Auto-posts to X without human | Draft under leash; publish only after human confirm |
| Every Grok tool is gated | mcp-assure gates calls on the assured host path; shell is separate |
| We red-teamed the stack (formal RT) | Operator hold-tests: unarmed / denylist / confirm-reject refuse |
| Public full CUA product | mcp-assure is public; browser- + desktop-leash are local today |

**Also forbidden:** win-rate %, “unbreakable”, “would have stopped [incident] end-to-end.”
