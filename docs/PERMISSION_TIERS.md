# desktop-leash permission tiers

See full roadmap: `~/ops/DESKTOP_LEASH_PLAN.md`

| Tier | Phase | Arm | Actions |
|------|-------|-----|---------|
| **D0** | 1–2 | no | `status` |
| **D1** | 1–2 | yes | apps, windows, displays, screenshot, frontmost |
| **D2** | 2 | yes | `desktop.focus` (allowlist only) |
| **D3** | 2 | yes | click / type / press / scroll if **frontmost allowlisted** |
| **D4** | 3 | yes + confirm | high-blast (not built) |

Phase 2 enforces app allowlist + denylist + input velocity (~40/min).
