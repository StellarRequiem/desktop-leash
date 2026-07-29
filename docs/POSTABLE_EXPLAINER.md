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
• Unarmed / wrong app / disabled Post → refuse (we red-teamed this)
• High-blast needs explicit confirm — not silent execute

pip install mcp-assure && mcp-assure check
# browser-leash + desktop-leash are local control planes on this machine

Not a full SOC. Not unattended OS takeover.
```

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
when React won’t enable Post. Hold-test: unarmed path refused.

desktop-leash (local) — Phase 4 computer-use path for the rest of the Mac:
screenshot, list apps/windows, focus allowlisted apps, click/type/press/scroll.
Quit and Return require confirm --yes. Password managers denylisted.

How this changes work:
Before: agent either stuck in chat or trusted with everything.
Now: split surfaces — shell for code, browser-leash for Chrome, desktop-leash for other GUI —
each with arm, allowlists, receipts, and human gates on high blast.

That’s how you get leverage without ambient authority.
```

---

## What not to claim

- “Full computer use like a human with no limits”
- “Stops all agent attacks / full SOC”
- “Auto-posts to X without human”
- “Every Grok tool is gated” (shell tools are separate; mcp-assure is for wired hosts)
