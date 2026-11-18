#!/usr/bin/env python3
"""Check that easyTravel and OneAgent are running on this VM.

usage: bin/check.py          (set ET_HOST=<address> to check another machine)
"""
import shutil, subprocess
from etlib import BACKEND, FRONTEND, LAUNCHER, get

ok = True
for name, url in [("Web Launcher", f"{LAUNCHER}/main"),
                  ("Customer Frontend", f"{FRONTEND}/"),
                  ("Business Backend", f"{BACKEND}/services/ConfigurationService")]:
    status, sec = get(url)
    good = status > 0          # any HTTP answer means the component is up
    ok &= good
    print(f"{name:<18} {url:<53} {('HTTP %d' % status) if status else 'no answer':<10} {sec * 1000:6.0f} ms  {'OK' if good else 'NOT OK'}")

if shutil.which("systemctl"):
    state = subprocess.run(["systemctl", "is-active", "oneagent"], capture_output=True, text=True).stdout.strip() or "unknown"
    print(f"{'OneAgent service':<18} {"systemctl is-active oneagent":<53} {state:<10} {'':>9}  {'OK' if state == 'active' else 'NOT OK'}")
    ok &= state == "active"
print("all checks passed" if ok else "some checks failed: see the troubleshooting table in the Lab Guide")
