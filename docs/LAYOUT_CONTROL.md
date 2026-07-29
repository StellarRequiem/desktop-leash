# Layout control — how agents must see the desktop

## The problem

Full-screen click guessing fails when windows split the display (e.g. Terminal left, Chrome right).  
Agents must **map windows first**, then click **inside a window frame**.

## Rule

```
layout → pick window → screenshot_window (optional) → click_window (rel or local)
```

Never: `click --x 1600 --y 700` without knowing which window owns that point.

## Commands

```bash
# 1) See everything
python3 ~/desktop-leash/bridge/client.py layout
# → frames_by_app: Terminal {x,y,w,h}, Google Chrome {x,y,w,h}, ...

# 2) Capture only Chrome
python3 ~/desktop-leash/bridge/client.py shot-window --app "Google Chrome" --out /tmp/chrome.png

# 3) Click inside Chrome (normalized 0..1 of that window)
python3 ~/desktop-leash/bridge/client.py click-window \
  --app "Google Chrome" --rel-x 0.92 --rel-y 0.88
# Post-ish bottom-right of THAT window, not the whole screen
```

## Coordinate spaces

| Space | Meaning |
|-------|---------|
| **global** | Screen top-left (0,0); what CGEvent / System Events click use |
| **local** | Offset inside window frame (0,0 = window top-left) |
| **relative** | 0..1 within window width/height |

`click_window` converts local/relative → global using live bounds.

## Agent SOP

1. `layout` at start of any GUI step (or after window resize/move)  
2. Read `frames_by_app` / frontmost  
3. Prefer `shot-window` over full desktop shot for web/UI work  
4. Prefer `click_window --rel-x/y` over global x/y  
5. Prefer browser-leash for Chrome when extension is alive  

## Version

desktop-leash **0.7.0** phase 7 `layout-control`
