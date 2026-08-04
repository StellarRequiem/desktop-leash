# Claim gate — desktop-leash

Public language must stay **≤ evidence**. Updated 2026-08-03.

## Allowed

| Claim | Evidence |
|-------|----------|
| Local macOS desktop control plane (loopback) | this repo · port **8757** |
| Sticky ARM; app allowlist + hard denylist | bridge · profiles |
| D4 dual-control for high-blast (quit, Return, …) | confirm queue + D4 session |
| Layout-first window-local control | `desktop.layout` · `click_window` · docs/LAYOUT_CONTROL.md |
| CUA observe depth (AX, region, ax_click) | phase 6+ |
| Operator hold-tests: NOT_ARMED, denylist, confirm-reject | tests + live smoke via agent-control |

## Not allowed

| Overclaim | Why |
|-----------|-----|
| Unlimited human-equivalent CUA | Allowlist, arm, budgets, D4 |
| Unattended OS takeover | DISARM stops authority |
| Password manager automation | Hard denylist |
| Full SOC / EDR | Wrong product class |
| Cross-OS desktop product | macOS-focused local plane |

## Versions (disk)

| Field | Value |
|-------|--------|
| Version | **0.7.0** (phase 7 layout-control era) |
| Profile | `cua` wider allow + hard deny |

## Recommended wording

> **desktop-leash** is a local macOS desktop control plane: arm-gated observe and allowlisted input, layout-first targeting, human confirm on high-blast — not unattended OS takeover.
