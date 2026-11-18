#!/usr/bin/env python3
"""Turn easyTravel problem patterns on and off through the Business Backend (port 8091).

usage: bin/pattern.py on  CreditCardCheckError500
       bin/pattern.py off CreditCardCheckError500
       bin/pattern.py reset        # turn off every pattern this course uses
       bin/pattern.py list         # the patterns this course uses

The backend answers HTTP 202 (Accepted) even for a name it does not know, so check the
spelling, and check the Problem Patterns list in the Web Launcher (port 8094) if in doubt.
"""
import sys
from datetime import datetime, timezone
from etlib import BACKEND, PATTERNS, set_pattern

args = sys.argv[1:]
if not args or args[0] not in ("on", "off", "reset", "list") or (args[0] in ("on", "off") and len(args) != 2):
    sys.exit(__doc__)
if args[0] == "list":
    for name, what in PATTERNS.items():
        print(f"{name:<24} {what}")
    sys.exit(0)
todo = [(n, False) for n in PATTERNS] if args[0] == "reset" else [(args[1], args[0] == "on")]
failed = False
for name, enabled in todo:
    status = set_pattern(name, enabled)
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    note = "" if name in PATTERNS else "  (not a pattern this course uses: check the spelling)"
    if status == 0:
        print(f"{now}  {name}: no answer from {BACKEND}: is easyTravel running?")
        failed = True
    else:
        print(f"{now}  {name} -> {'on' if enabled else 'off'} (HTTP {status}){note}")
        failed |= status >= 400
sys.exit(1 if failed else 0)
