#!/usr/bin/env python3
"""Print one metric per minute as a bar chart in the terminal.

usage: bin/series.py FILE --where key=value [--where key=value] --field NAME [--from HH:MM] [--to HH:MM] [--every N]
example: bin/series.py incident/service_metrics.csv --where service=CreditCardValidation --field p95_ms --from 13:40 --to 14:50 --every 2
"""
import argparse, csv

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--where", action="append", default=[])
ap.add_argument("--field", required=True)
ap.add_argument("--from", dest="t0", default="00:00")
ap.add_argument("--to", dest="t1", default="23:59")
ap.add_argument("--every", type=int, default=1)
ap.add_argument("--width", type=int, default=50)
a = ap.parse_args()
cond = [w.split("=", 1) for w in a.where]
rows = [r for r in csv.DictReader(open(a.file))
        if all(r.get(k) == v for k, v in cond) and a.t0 <= r["timestamp"][11:16] <= a.t1]
rows = rows[::a.every]
vals = [float(r[a.field]) for r in rows]
top = max(vals) if vals else 1
print(f"{a.field} per minute" + (f" ({', '.join(f'{k}={v}' for k, v in cond)})" if cond else ""))
for r, v in zip(rows, vals):
    bar = "#" * max(1, round(v / top * a.width)) if v > 0 else ""
    print(f"{r['timestamp'][11:16]}  {v:>9g}  {bar}")
