#!/usr/bin/env python3
"""Run a timed sequence of easyTravel problem patterns.

usage: bin/scenario.py lab12            # 12 minutes, for Lab 1.2
       bin/scenario.py lab13            # 20 minutes, for Labs 1.3 and 1.4
       bin/scenario.py lab13 --speed 10 # 10 times faster (for a quick test)

Keep the easyTravel load running (Web Launcher, scenario UEM > Standard) while the scenario runs.
Ctrl+C stops the scenario and turns its patterns off.
"""
import sys, time
from datetime import datetime, timezone
from etlib import set_pattern

SCENARIOS = {
    # minute from start -> pattern that is on from then (None = all off); a final None entry ends the run
    "lab12": [(0, None), (3, "CreditCardCheckError500"), (9, None), (12, "END")],
    "lab13": [(0, None), (5, "CPULoadJourneyService"), (11, None), (13, "CreditCardCheckError500"), (17, None), (20, "END")],
}
name = sys.argv[1] if len(sys.argv) > 1 else ""
speed = float(sys.argv[sys.argv.index("--speed") + 1]) if "--speed" in sys.argv else 1.0
if name not in SCENARIOS:
    sys.exit(__doc__)
used = sorted({p for _, p in SCENARIOS[name] if p not in (None, "END")})


def all_off():
    for p in used:
        set_pattern(p, False)


start = time.time()
print(f"scenario {name} started at {datetime.now(timezone.utc):%H:%M:%S} UTC" + (f" (speed x{speed:g})" if speed != 1 else ""), flush=True)
current = None
try:
    for minute, pattern in SCENARIOS[name]:
        wait = start + minute * 60 / speed - time.time()
        if wait > 0:
            time.sleep(wait)
        stamp = f"+{minute:02d}:00  {datetime.now(timezone.utc):%H:%M:%S} UTC"
        if pattern == "END":
            all_off()
            print(f"{stamp}  scenario finished; all its patterns are off", flush=True)
            break
        if current:
            status = set_pattern(current, False)
            print(f"{stamp}  {current} off (HTTP {status})", flush=True)
        if pattern:
            status = set_pattern(pattern, True)
            print(f"{stamp}  {pattern} on (HTTP {status})", flush=True)
        elif not current:
            all_off()
            print(f"{stamp}  normal: no problem pattern on", flush=True)
        current = pattern
except KeyboardInterrupt:
    all_off()
    print("\nstopped; all scenario patterns are off")
