# Threat model — desktop-leash

## Trust boundary

- Bridge on **127.0.0.1**
- Requires macOS **Accessibility** + **Screen Recording**
- Operator **ARM** + app allowlist + hard denylist

## Assets

- Screen contents (PII possible)  
- Ability to type/click in allowlisted apps  
- High-blast: quit / Return (may execute shell)

## Mitigations

- Deny-by-default actions  
- App allowlist + password-manager denylist  
- D4 dual-control session + confirm queue  
- Velocity ceilings  
- Redacted AX snapshots  

## Non-goals

- Cross-user / remote desktop  
- Unlimited ambient CUA  
- Enterprise EDR replacement  
