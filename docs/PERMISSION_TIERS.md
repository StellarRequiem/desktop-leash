# desktop-leash permission tiers

See full roadmap: `~/ops/DESKTOP_LEASH_PLAN.md`

| Tier | Phase | Arm | Actions |
|------|-------|-----|---------|
| **D0** | 1 | no | `status` |
| **D1** | 1 | yes | `desktop.apps`, `desktop.windows`, `desktop.displays`, `desktop.screenshot` |
| **D2** | 2 | yes | focus allowlisted app |
| **D3** | 2 | yes | click / type / key / scroll in allowlist |
| **D4** | 3 | yes + confirm | high-blast |

Phase 1 refuses D2+ with `PHASE1_LOCKED`.
