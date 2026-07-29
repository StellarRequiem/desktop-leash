# Phase 1 smoke checklist

```bash
python3 ~/desktop-leash/bridge/server.py &   # or already running
python3 ~/desktop-leash/bridge/client.py status   # phase=1, armed maybe false
python3 ~/desktop-leash/bridge/client.py apps     # expect NOT_ARMED if disarmed
python3 ~/desktop-leash/bridge/client.py arm
python3 ~/desktop-leash/bridge/client.py apps
python3 ~/desktop-leash/bridge/client.py windows
python3 ~/desktop-leash/bridge/client.py screenshot --out /tmp/desktop-leash-smoke.png
python3 ~/desktop-leash/bridge/client.py click    # expect PHASE1_LOCKED (client) or refuse
```
