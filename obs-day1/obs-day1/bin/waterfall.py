#!/usr/bin/env python3
"""Draw the waterfall of one trace from a spans file (JSON Lines).

usage: bin/waterfall.py TRACE_ID [incident/spans.jsonl]
Each line: offset from the trace start, duration, service, span name, and a bar placed on the time axis.
"""
import json, sys
from datetime import datetime

tid = sys.argv[1]
path = sys.argv[2] if len(sys.argv) > 2 else "incident/spans.jsonl"
sp = [s for s in map(json.loads, open(path)) if s["trace.id"] == tid]
if not sp:
    sys.exit(f"no spans for trace {tid}")
t = lambda x: datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp()
t0 = min(t(s["start_time"]) for s in sp)
total = max(t(s["end_time"]) for s in sp) - t0
kids = {}
for s in sp:
    kids.setdefault(s["span.parent_id"], []).append(s)
W = 40
L = 80          # width of the span column
print(f"trace {tid}  {len(sp)} spans  {total*1000:.0f} ms")
print(f"{'start':>8} {'duration':>9}  {'span':<{L}} timeline (0 to {total*1000:.0f} ms)")
def walk(pid, depth):
    for s in sorted(kids.get(pid, []), key=lambda x: x["start_time"]):
        off = t(s["start_time"]) - t0
        a = int(off / total * W)
        b = max(1, int(s["duration_ms"] / 1000 / total * W))
        mark = "!" if s["request.is_failed"] else "="
        name = ("  " * depth + f"{s['dt.service.name']}: {s['span.name']}")[:L]
        print(f"{off*1000:>6.0f}ms {s['duration_ms']:>7.0f}ms  {name:<{L}} |{' '*a}{mark*b}{' '*(W-a-b)}|")
        walk(s["span.id"], depth + 1)
walk(None, 0)
print("bars: = span time, ! failed span")
