# Anti-patterns — desktop-leash

## Never

| Anti-pattern | Why |
|--------------|-----|
| Screenshot then post raw to X without scrub | PII, secrets, personal chats on screen |
| Focus / type into **1Password, Bitwarden, Keychain, Passwords** | Denylisted; credential surface |
| Auto `confirm --yes` without operator in-thread OK | Breaks D4 human gate |
| Prefer desktop type into Terminal over shell tool | Opaque, easy to execute wrong command |
| Use desktop-leash for Chrome/X when browser-leash works | Weaker host/session model for web |
| Arm forever across multi-day absence | Sticky arm is for a **session**; DISARM when done for the day |
| Claim “full CUA / we control the Mac like a human” | Overclaim until hold-tests + allowlist discipline are public evidence |
| `press return` in Terminal without reading the line | May execute shell as user |
| Expand allowlist to “all apps” | Defeats the plane |

## Careful

| Pattern | Guidance |
|---------|----------|
| Screenshot | Local path only; delete when done; never commit captures/ |
| Window titles in receipts | May contain secrets/URLs — don’t paste receipts publicly |
| Click x,y | Screen-global; multi-monitor easy to miss; prefer focus+type when possible |
| Notes / Messages content | Notes is allowlisted for demo; treat content as private |
| OBS / streaming | May capture agent activity live — operator awareness |

## Prefer instead

| Instead of… | Do… |
|-------------|-----|
| Type `git commit` in Terminal GUI | Shell `git` tools |
| Click around GitHub in desktop coords | browser-leash navigate/click |
| Quit random apps | Only allowlisted + D4 confirm |
| Disable confirm for speed | Keep `DESKTOP_LEASH_REQUIRE_CONFIRM=1` |

## Operator adversarial checks (keep green)

1. Disarmed → any D1+ → `NOT_ARMED`  
2. Frontmost not allowlisted → input refused  
3. Denylist app → `APP_DENIED`  
4. Return/quit without confirm → `CONFIRM_REQUIRED`  
5. confirm --no → no side effect  
