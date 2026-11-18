#!/usr/bin/env python3
"""Summarise service metrics (RED) for a time window, one line per service and endpoint.

usage: bin/window.py incident/service_metrics.csv --from 13:00 --to 13:58
Requests and failures are summed; p50 and p95 are the median of the per-minute values.
"""
import argparse, csv, statistics

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--from", dest="t0", required=True)
ap.add_argument("--to", dest="t1", required=True)
a = ap.parse_args()
groups = {}
for r in csv.DictReader(open(a.file)):
    if a.t0 <= r["timestamp"][11:16] < a.t1:
        groups.setdefault((r["service"], r["endpoint"]), []).append(r)
ws = max([len("service")] + [len(s) for s, _ in groups]) + 2
we = max([len("endpoint")] + [len(e) for _, e in groups]) + 2
print(f"{a.t0} to {a.t1} UTC")
print(f"{'service':<{ws}}{'endpoint':<{we}}{'requests':>10}{'failures':>10}{'fail %':>8}{'p50 ms':>9}{'p95 ms':>9}")
for (svc, ep), rows in sorted(groups.items()):
    req = sum(int(r["requests"]) for r in rows)
    fail = sum(int(r["failures"]) for r in rows)
    p50 = statistics.median(float(r["p50_ms"]) for r in rows)
    p95 = statistics.median(float(r["p95_ms"]) for r in rows)
    print(f"{svc:<{ws}}{ep:<{we}}{req:>10,}{fail:>10,}{100 * fail / req:>8.2f}{p50:>9.0f}{p95:>9.0f}")
