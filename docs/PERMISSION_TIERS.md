# desktop-leash permission tiers

See full roadmap: `~/ops/DESKTOP_LEASH_PLAN.md`

| Tier | Phase | Arm | Actions |
|------|-------|-----|---------|
| **D0** | 1–2 | no | `status` |
| **D1** | 1–2 | yes | apps, windows, displays, screenshot, frontmost |
| **D2** | 2 | yes | `desktop.focus` (allowlist only) |
| **D3** | 2 | yes | click / type / press / scroll if **frontmost allowlisted** |
| **D4** | 3 | yes + **confirm** | quit app; press Return/Enter; risky type patterns |

Phase 3: D4 returns `CONFIRM_REQUIRED` → `client.py confirm --id … --yes|--no` (TTL ~120s).  
Phase 5: D4 also needs dual-control session: `client.py d4-session --open [--ttl 300]` first;  
then confirm. AX observe: `client.py ax`. Version **0.5.0**.  
Allowlist + denylist + velocity still apply.
