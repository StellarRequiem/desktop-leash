# Load / permissions — desktop-leash Phase 1

## 1. Start bridge

```bash
python3 ~/desktop-leash/bridge/server.py
# http://127.0.0.1:8757
```

Background:

```bash
nohup python3 ~/desktop-leash/bridge/server.py >>~/desktop-leash/receipts/bridge.log 2>&1 &
```

## 2. macOS Privacy grants

### Screen Recording (screenshots)

1. System Settings → **Privacy & Security** → **Screen Recording**  
2. Enable the terminal app that launches the bridge (e.g. **Terminal**, **Ghostty**, **iTerm**)  
3. If Python is listed separately, enable it  
4. Quit and restart the bridge after granting  

Without this: `screenshot` returns `SCREENSHOT_FAIL`.

### Accessibility (apps / windows)

1. System Settings → **Privacy & Security** → **Accessibility**  
2. Enable the same terminal / python host  
3. Restart bridge  

Without this: `apps` / `windows` may fail or return empty / incomplete.

## 3. Arm (sticky toggle)

```bash
python3 ~/desktop-leash/bridge/client.py arm     # ON until disarm
python3 ~/desktop-leash/bridge/client.py disarm  # OFF
```

No 15-minute timer by default (`DESKTOP_LEASH_ARM_TTL=0`).

## 4. Smoke

```bash
python3 ~/desktop-leash/bridge/client.py status
python3 ~/desktop-leash/bridge/client.py arm
python3 ~/desktop-leash/bridge/client.py apps
python3 ~/desktop-leash/bridge/client.py windows
python3 ~/desktop-leash/bridge/client.py screenshot --out /tmp/desktop-leash-smoke.png
ls -la /tmp/desktop-leash-smoke.png
```

## 5. Phase lock

`click` / `type` and other D2+ actions return `PHASE1_LOCKED` until Phase 2 is built.
