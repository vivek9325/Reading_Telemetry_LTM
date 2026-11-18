#!/usr/bin/env python3
"""Build the INC data bundle for Day 1: easyTravel in production, 12 Nov 2026, 12:00-15:00 UTC.

A deployment of CreditCardValidation v2.8.0 at 13:58 lowers the database connection pool
from 50 to 10. Under lunchtime traffic the pool saturates: requests queue for a
connection, time out after 2,000 ms, and bookings slow down and fail. A rollback
at 14:41 ends it. Output is identical on every run (fixed seed).
"""
import csv, heapq, json, math, os, random
from datetime import datetime, timedelta, timezone

R = random.Random(20261112)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "incident")
T0 = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
MIN = 180
DEPLOY = 13 * 60 + 58          # minute of day (UTC)
ROLLBACK = 14 * 60 + 41
DEPLOY_S = (DEPLOY - 12 * 60) * 60 + 15     # pool 50 -> 10 at 13:58:15 (restart done)
ROLLBACK_S = (ROLLBACK - 12 * 60) * 60 + 14  # pool 10 -> 50 at 14:41:14
TIMEOUT = 2.0                  # pool acquire timeout, seconds
SAMPLE = 150                   # 1 in 150 booking traces exported

def ts(sec):                   # seconds from T0 -> ISO string with ms
    return (T0 + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def rate_per_min(m):           # bookings per minute, m = minute from T0
    pts = [(0, 600), (60, 980), (90, 1250), (120, 1450), (135, 1520), (150, 1460), (180, 1100)]
    for (a, va), (b, vb) in zip(pts, pts[1:]):
        if a <= m <= b:
            return va + (vb - va) * (m - a) / (b - a)
    return pts[-1][1]

def hexid(n):
    return "".join(R.choice("0123456789abcdef") for _ in range(n))

# ---------------------------------------------------------------- simulate the payment pool (M/G/c with timeout)
arrivals = []
t = 0.0
while t < MIN * 60:
    lam = rate_per_min(t / 60) / 60.0
    t += R.expovariate(lam)
    if t < MIN * 60:
        arrivals.append(t)

def pool_size(sec):
    return 10 if DEPLOY_S <= sec < ROLLBACK_S else 50

def hold_time(sec):
    # card authorizer call + insert; v2.8.0 adds a fraud-check query that holds the connection ~120 ms longer
    base = R.lognormvariate(math.log(0.30), 0.22)      # card authorizer round trip ~300 ms
    extra = R.lognormvariate(math.log(0.12), 0.25) if DEPLOY_S <= sec < ROLLBACK_S else 0.0
    return base + extra + R.uniform(0.004, 0.009)

free_at = []            # heap of times connections become free (busy connections)
busy = 0
waiting = []            # FIFO of request indices waiting
reqs = []               # per request: arrival, wait, hold, failed, conn_free_time
events = []             # (time, kind, idx) min-heap
for i, a in enumerate(arrivals):
    heapq.heappush(events, (a, 1, i))
pool_samples = {}       # minute -> list of (active, waiting)
inflight = []
res = [None] * len(arrivals)
q = []                  # waiting queue (arrival idx)
qi = 0
active = 0
next_sample = 0.0
while events:
    now, kind, i = heapq.heappop(events)
    while next_sample <= now and next_sample < MIN * 60:
        live = [j for j in q[qi:] if res[j] is None]
        pool_samples.setdefault(int(next_sample // 60), []).append((active, len(live)))
        next_sample += 5.0
    if kind == 1:                       # arrival
        if active < pool_size(now):
            active += 1
            h = hold_time(now)
            res[i] = (0.0, h, False)
            heapq.heappush(events, (now + h, 0, i))
        else:
            q.append(i)
            heapq.heappush(events, (now + TIMEOUT, 2, i))
    elif kind == 2:                     # timeout of a waiting request
        if res[i] is None:
            res[i] = (TIMEOUT, 0.0, True)
    else:                               # a connection is released
        active -= 1
        while qi < len(q) and res[q[qi]] is not None:
            qi += 1
        cap = pool_size(now)
        while active < cap and qi < len(q):
            j = q[qi]; qi += 1
            if res[j] is not None:
                continue
            w = now - arrivals[j]
            active += 1
            h = hold_time(now)
            res[j] = (w, h, False)
            heapq.heappush(events, (now + h, 0, j))

# ---------------------------------------------------------------- per-request latencies through the chain
recs = []
for i, a in enumerate(arrivals):
    w, h, failed = res[i]
    psp_err = (not failed) and R.random() < 0.0009          # background card-authorizer 5xx
    pay = (TIMEOUT + R.uniform(0.002, 0.006)) if failed else (w + h + R.uniform(0.003, 0.008))
    inv = R.lognormvariate(math.log(0.024), 0.25)
    orders_own = R.uniform(0.008, 0.016)
    orders = inv + pay + orders_own + R.uniform(0.002, 0.004) * 2
    front = orders + R.uniform(0.006, 0.012) + R.uniform(0.001, 0.003)
    recs.append(dict(i=i, start=a, wait=w, hold=h, failed=failed or psp_err, pool_timeout=failed,
                     psp_err=psp_err, inv=inv, pay=pay, orders=orders, front=front))

def pct(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(math.ceil(p / 100 * len(s))) - 1))
    return s[k]

os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- service metrics (per minute)
svc_rows = []
browse_rows = []
by_min = {}
for r in recs:
    by_min.setdefault(int(r["start"] // 60), []).append(r)
for m in range(MIN):
    rs = by_min.get(m, [])
    stamp = (T0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:00Z")
    for svc, key, ep in [("easyTravel Customer Frontend", "front", "/orange-booking-payment.jsf"), ("BookingService", "orders", "storeBooking"),
                         ("CreditCardValidation", "pay", "validateCreditCard"), ("JourneyService", "inv", "getJourneyById")]:
        lat = [r[key] * 1000 for r in rs]
        fails = sum(1 for r in rs if r["failed"]) if svc != "JourneyService" else 0
        svc_rows.append([stamp, svc, ep, len(rs), fails, round(pct(lat, 50), 1), round(pct(lat, 95), 1), round(pct(lat, 99), 1)])
    # browsing traffic on easyTravel Customer Frontend (unaffected): ~9x bookings
    n = int(rate_per_min(m) * 9 + R.gauss(0, 80))
    lat = [R.lognormvariate(math.log(38), 0.35) for _ in range(400)]
    browse_rows.append([stamp, "easyTravel Customer Frontend", "/orange.jsf", n, sum(1 for _ in range(n) if R.random() < 0.0006),
                        round(pct(lat, 50), 1), round(pct(lat, 95), 1), round(pct(lat, 99), 1)])
with open(os.path.join(OUT, "service_metrics.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "service", "endpoint", "requests", "failures", "p50_ms", "p95_ms", "p99_ms"])
    rows = svc_rows + browse_rows
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    w.writerows(rows)

# ---------------------------------------------------------------- response time histogram for CreditCardValidation (per minute, 250 ms buckets)
with open(os.path.join(OUT, "payment_latency_histogram.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "service", "bucket_ms", "requests"])
    for m in range(MIN):
        stamp = (T0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:00Z")
        cnt = {}
        for r in by_min.get(m, []):
            b = min(int(r["pay"] * 1000 // 250) * 250, 2750)
            cnt[b] = cnt.get(b, 0) + 1
        for b in range(0, 3000, 250):
            w.writerow([stamp, "CreditCardValidation", f"{b}-{b + 250}", cnt.get(b, 0)])

# ---------------------------------------------------------------- host metrics + pool metrics (per minute)
hosts = {"web-01": 4, "app-01": 8, "pay-01": 4, "db-01": 8}
host_rows = []
for m in range(MIN):
    stamp = (T0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:00Z")
    load = rate_per_min(m) / 1520
    minute = 12 * 60 + m
    incident = DEPLOY + 3 <= minute < ROLLBACK + 2
    served = 1.0 - (sum(1 for r in by_min.get(m, []) if r["pool_timeout"]) / max(1, len(by_min.get(m, []))))
    for h, cores in hosts.items():
        if h == "web-01":
            cpu = 18 + 34 * load
        elif h == "app-01":
            cpu = 14 + 30 * load
        elif h == "pay-01":
            cpu = (10 + 26 * load) * (served if incident else 1.0)
        else:
            cpu = (12 + 22 * load) * (served if incident else 1.0)
        cpu = max(2.0, cpu + R.gauss(0, 1.6))
        lpc = cpu / 100 * 0.95 + R.gauss(0, 0.03)
        mem = {"web-01": 41, "app-01": 58, "pay-01": 47, "db-01": 72}[h] + R.gauss(0, 0.6)
        host_rows.append([stamp, h, cores, round(cpu, 1), round(max(0.02, lpc), 2), round(mem, 1)])
with open(os.path.join(OUT, "host_metrics.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "host", "cpu_cores", "cpu_usage_pct", "load_per_core", "memory_usage_pct"])
    w.writerows(host_rows)

pool_rows = []
for m in range(MIN):
    stamp = (T0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:00Z")
    smp = pool_samples.get(m, [(0, 0)])
    mx = 10 if DEPLOY <= 12 * 60 + m < ROLLBACK else 50  # pool size at the end of the minute
    rs = by_min.get(m, [])
    pool_rows.append([stamp, "CreditCardValidation", mx, round(sum(a for a, _ in smp) / len(smp), 1), max(a for a, _ in smp),
                      round(sum(wq for _, wq in smp) / len(smp), 1), max(wq for _, wq in smp),
                      sum(1 for r in rs if r["pool_timeout"])])
with open(os.path.join(OUT, "pool_metrics.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "service", "pool_max", "active_avg", "active_max", "waiting_avg", "waiting_max", "acquire_timeouts"])
    w.writerows(pool_rows)

# ---------------------------------------------------------------- traces (sampled) + logs
spans, logs = [], []
def span(trace, sid, parent, svc, name, kind, st, dur, failed=False, **attrs):
    d = {"trace.id": trace, "span.id": sid, "span.parent_id": parent, "dt.service.name": svc, "span.name": name,
         "span.kind": kind, "start_time": ts(st), "end_time": ts(st + dur), "duration_ms": round(dur * 1000, 1),
         "request.is_failed": failed}
    d.update(attrs)
    spans.append(d)

def log(sec, level, svc, host, msg, trace=None, sid=None):
    logs.append({"timestamp": ts(sec), "loglevel": level, "service.name": svc, "host.name": host,
                 "content": msg, "trace_id": trace, "span_id": sid})

order_no = 7310000
pay_hosts = ["pay-01"]
sampled = set(i for i in range(len(recs)) if R.random() < 1 / SAMPLE)
for r in recs:
    order_no += 1
    i, s = r["i"], r["start"]
    keep = i in sampled
    trace = hexid(32)
    ids = [hexid(16) for _ in range(12)]
    f_front, f_ord_c, f_ord, f_inv_c, f_inv, f_db1, f_pay_c, f_pay, f_acq, f_db2, f_fraud, f_psp = ids
    t_front = s
    t_ord_c = s + 0.004
    t_ord = t_ord_c + 0.001
    t_inv_c = t_ord + 0.003
    t_inv = t_inv_c + 0.001
    inv_d = r["inv"]
    t_pay_c = t_inv_c + inv_d + 0.003
    t_pay = t_pay_c + 0.001
    pay_d = r["pay"]
    status = 502 if r["failed"] else 200
    if keep:
        span(trace, f_front, None, "easyTravel Customer Frontend", "/orange-booking-payment.jsf", "server", t_front, r["front"], r["failed"],
             **{"http.request.method": "POST", "http.route": "/orange-booking-payment.jsf", "http.response.status_code": status, "host.name": "web-01"})
        span(trace, f_ord_c, f_front, "easyTravel Customer Frontend", "POST /services/BookingService/storeBooking", "client", t_ord_c, r["orders"] + 0.002, r["failed"],
             **{"server.address": "app-01", "http.response.status_code": status, "host.name": "web-01"})
        span(trace, f_ord, f_ord_c, "BookingService", "storeBooking", "server", t_ord, r["orders"], r["failed"],
             **{"http.request.method": "POST", "http.route": "/services/BookingService/storeBooking", "http.response.status_code": status, "host.name": "app-01"})
        span(trace, f_inv_c, f_ord, "BookingService", "POST /services/JourneyService/getJourneyById", "client", t_inv_c, inv_d + 0.002, False,
             **{"server.address": "app-01", "http.response.status_code": 200, "host.name": "app-01"})
        span(trace, f_inv, f_inv_c, "JourneyService", "getJourneyById", "server", t_inv, inv_d, False,
             **{"http.request.method": "POST", "http.route": "/services/JourneyService/getJourneyById", "http.response.status_code": 200, "host.name": "app-01"})
        span(trace, f_db1, f_inv, "JourneyService", "SELECT Journey", "client", t_inv + 0.002, inv_d * 0.55, False,
             **{"db.system": "derby", "db.namespace": "easyTravelBusiness", "db.query.text": "SELECT j.id, j.seats_left FROM Journey j WHERE j.id = ?", "host.name": "app-01"})
        span(trace, f_pay_c, f_ord, "BookingService", "POST /services/CreditCardValidation/validateCreditCard", "client", t_pay_c, pay_d + 0.002, r["failed"],
             **{"server.address": "pay-01", "http.response.status_code": 503 if r["pool_timeout"] else (502 if r["psp_err"] else 200), "host.name": "app-01"})
        span(trace, f_pay, f_pay_c, "CreditCardValidation", "validateCreditCard", "server", t_pay, pay_d, r["failed"],
             **{"http.request.method": "POST", "http.route": "/services/CreditCardValidation/validateCreditCard", "http.response.status_code": 503 if r["pool_timeout"] else (502 if r["psp_err"] else 200), "host.name": "pay-01"})
        acq = r["wait"] if not r["pool_timeout"] else TIMEOUT
        span(trace, f_acq, f_pay, "CreditCardValidation", "HikariPool-1 getConnection", "internal", t_pay + 0.001, max(acq, 0.0002), r["pool_timeout"],
             **{"db.client.connection.pool.name": "HikariPool-1", "host.name": "pay-01"})
        if not r["pool_timeout"]:
            t_db = t_pay + 0.001 + acq + 0.0005
            fraud = DEPLOY_S <= t_pay < ROLLBACK_S
            q_d = R.uniform(0.003, 0.007)
            span(trace, f_db2, f_pay, "CreditCardValidation", "INSERT CreditCardCheck", "client", t_db, q_d, False,
                 **{"db.system": "derby", "db.namespace": "easyTravelBusiness", "db.query.text": "INSERT INTO CreditCardCheck (booking_id, amount, status) VALUES (?, ?, ?)", "host.name": "pay-01"})
            t_next = t_db + q_d + 0.0005
            if fraud:
                fq = r["hold"] * 0.27
                span(trace, f_fraud, f_pay, "CreditCardValidation", "SELECT fraud_score", "client", t_next, fq, False,
                     **{"db.system": "derby", "db.namespace": "easyTravelBusiness", "db.query.text": "SELECT SUM(amount) FROM CreditCardCheck WHERE card_hash = ? AND created_at > ?", "host.name": "pay-01"})
                t_next += fq + 0.0005
            psp_d = max(0.05, t_pay + pay_d - t_next - 0.002)
            span(trace, f_psp, f_pay, "CreditCardValidation", "POST cards.example.net/v1/authorize", "client", t_next, psp_d, r["psp_err"],
                 **{"server.address": "cards.example.net", "http.response.status_code": 502 if r["psp_err"] else 200, "host.name": "pay-01"})
        # INFO logs for exported traces
        log(t_front + 0.001, "INFO", "easyTravel Customer Frontend", "web-01", f"Booking started travellers={R.randint(1, 5)}", trace, f_front)
        log(t_ord + 0.002, "INFO", "BookingService", "app-01", f"Storing booking booking_id={order_no}", trace, f_ord)
        log(t_inv + inv_d - 0.001, "INFO", "JourneyService", "app-01", f"Journey available for booking_id={order_no}", trace, f_inv)
        if not r["failed"]:
            log(t_pay + pay_d - 0.001, "INFO", "CreditCardValidation", "pay-01", f"Credit card validated booking_id={order_no} auth_ms={int(psp_d*1000)}", trace, f_pay)
            log(t_ord + r["orders"] - 0.001, "INFO", "BookingService", "app-01", f"Booking stored booking_id={order_no} status=CONFIRMED", trace, f_ord)
    # WARN/ERROR logs for every request (all traces)
    if r["pool_timeout"]:
        log(t_pay + TIMEOUT, "ERROR", "CreditCardValidation", "pay-01",
            "HikariPool-1 - Connection is not available, request timed out after 2000ms. (total=10, active=10, idle=0, waiting=%d)" % R.randint(8, 30),
            trace, f_pay)
        log(t_pay + TIMEOUT + 0.001, "ERROR", "CreditCardValidation", "pay-01",
            f"Validation failed booking_id={order_no}: org.springframework.jdbc.CannotGetJdbcConnectionException: Failed to obtain JDBC Connection", trace, f_pay)
        log(t_pay + pay_d + 0.003, "ERROR", "BookingService", "app-01",
            f"CreditCardValidation call failed booking_id={order_no} status=503 after {int(pay_d*1000)} ms", trace, f_ord)
        log(t_front + r["front"], "WARN", "easyTravel Customer Frontend", "web-01", f"Booking failed status=502 booking_id={order_no}", trace, f_front)
    elif r["psp_err"]:
        log(t_pay + pay_d, "ERROR", "CreditCardValidation", "pay-01", f"Card authorizer returned 502 for booking_id={order_no}", trace, f_pay)
        log(t_pay + pay_d + 0.003, "ERROR", "BookingService", "app-01", f"CreditCardValidation call failed booking_id={order_no} status=502 after {int(pay_d*1000)} ms", trace, f_ord)
        log(t_front + r["front"], "WARN", "easyTravel Customer Frontend", "web-01", f"Booking failed status=502 booking_id={order_no}", trace, f_front)
    elif r["wait"] > 1.0 and keep:
        log(t_pay + r["wait"], "WARN", "CreditCardValidation", "pay-01",
            f"Slow connection acquire: waited {int(r['wait']*1000)} ms for HikariPool-1 booking_id={order_no}", trace, f_pay)

# deployment / lifecycle logs
dsec = (DEPLOY - 12 * 60) * 60
log(dsec + 4.0, "INFO", "CreditCardValidation", "pay-01", "Starting CreditCardValidation v2.8.0 using Java 21.0.5")
log(dsec + 9.8, "INFO", "CreditCardValidation", "pay-01", "HikariPool-1 - Starting... maximumPoolSize=10 connectionTimeout=2000ms")
log(dsec + 10.4, "INFO", "CreditCardValidation", "pay-01", "HikariPool-1 - Start completed.")
log(dsec + 11.0, "INFO", "CreditCardValidation", "pay-01", "Fraud check enabled: rule=card-velocity-30d")
rsec = (ROLLBACK - 12 * 60) * 60
log(rsec + 4.0, "INFO", "CreditCardValidation", "pay-01", "Starting CreditCardValidation v2.7.4 using Java 21.0.5")
log(rsec + 9.6, "INFO", "CreditCardValidation", "pay-01", "HikariPool-1 - Starting... maximumPoolSize=50 connectionTimeout=2000ms")
log(rsec + 10.2, "INFO", "CreditCardValidation", "pay-01", "HikariPool-1 - Start completed.")
# unrelated noise: a known recurring warning
for k in range(0, MIN * 60, 300):
    log(k + 17.3, "WARN", "JourneyService", "app-01", "Cache refresh took 1240 ms (threshold 1000 ms) cache=journey-catalog")
logs.sort(key=lambda x: x["timestamp"])
spans.sort(key=lambda x: (x["trace.id"], x["start_time"]))
with open(os.path.join(OUT, "logs.jsonl"), "w") as f:
    for x in logs:
        f.write(json.dumps(x) + "\n")
with open(os.path.join(OUT, "spans.jsonl"), "w") as f:
    for x in spans:
        f.write(json.dumps(x) + "\n")
print("bookings", len(recs), "pool timeouts", sum(r["pool_timeout"] for r in recs),
      "failed", sum(r["failed"] for r in recs), "traces", len(sampled), "spans", len(spans), "logs", len(logs))

# ---------------------------------------------------------------- events (simplified export of dt.davis.events + change events)
def at(hm, s=0):
    h, m = map(int, hm.split(":"))
    return datetime(2026, 11, 12, h, m, s, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

EVENTS = [
    dict(timestamp=at("12:40", 3), **{"event.kind": "DAVIS_EVENT", "event.category": "INFO", "event.type": "DEPLOYMENT", "event.name": "Deployment: easyTravel Customer Frontend 5.12.1", "dt.service.name": "easyTravel Customer Frontend", "event.status": "CLOSED", "event.end": at("12:40", 3)}),
    dict(timestamp=at("13:58", 2), **{"event.kind": "DAVIS_EVENT", "event.category": "INFO", "event.type": "DEPLOYMENT", "event.name": "Deployment: CreditCardValidation 2.8.0 (was 2.7.4)", "dt.service.name": "CreditCardValidation", "event.status": "CLOSED", "event.end": at("13:58", 2), "deployment.release": "2.8.0", "deployment.ci_link": "https://ci.example.com/credit-card-validation/builds/1842"}),
    dict(timestamp=at("13:58", 2), **{"event.kind": "DAVIS_EVENT", "event.category": "INFO", "event.type": "CONFIGURATION_CHANGE", "event.name": "Configuration change: CreditCardValidation spring.datasource.hikari.maximum-pool-size 50 -> 10", "dt.service.name": "CreditCardValidation", "event.status": "CLOSED", "event.end": at("13:58", 2)}),
    dict(timestamp=at("14:00", 15), **{"event.kind": "DAVIS_EVENT", "event.category": "CUSTOM", "event.type": "CUSTOM_ALERT", "event.name": "CreditCardValidation connection pool: threads waiting above 5 for 2 minutes", "dt.service.name": "CreditCardValidation", "event.status": "CLOSED", "event.end": at("14:43", 0)}),
    dict(timestamp=at("14:01", 0), **{"event.kind": "DAVIS_EVENT", "event.category": "SLOWDOWN", "event.type": "RESPONSE_TIME_DEGRADATION", "event.name": "Response time degradation", "dt.service.name": "CreditCardValidation", "endpoint.name": "validateCreditCard", "event.status": "CLOSED", "event.end": at("14:44", 0), "event.description": "Median response time 2.18 s instead of 0.31 s (baseline)"}),
    dict(timestamp=at("14:01", 30), **{"event.kind": "DAVIS_EVENT", "event.category": "SLOWDOWN", "event.type": "RESPONSE_TIME_DEGRADATION", "event.name": "Response time degradation", "dt.service.name": "BookingService", "endpoint.name": "storeBooking", "event.status": "CLOSED", "event.end": at("14:44", 30)}),
    dict(timestamp=at("14:03", 0), **{"event.kind": "DAVIS_EVENT", "event.category": "ERROR", "event.type": "FAILURE_RATE_INCREASE", "event.name": "Failure rate increase", "dt.service.name": "easyTravel Customer Frontend", "endpoint.name": "/orange-booking-payment.jsf", "event.status": "CLOSED", "event.end": at("14:44", 0), "event.description": "Failure rate 6.4 % instead of 0.1 % (baseline)"}),
    dict(timestamp=at("14:41", 2), **{"event.kind": "DAVIS_EVENT", "event.category": "INFO", "event.type": "DEPLOYMENT", "event.name": "Deployment: CreditCardValidation 2.7.4 (rollback)", "dt.service.name": "CreditCardValidation", "event.status": "CLOSED", "event.end": at("14:41", 2), "deployment.release": "2.7.4"}),
]
with open(os.path.join(OUT, "events.jsonl"), "w") as f:
    for e in sorted(EVENTS, key=lambda e: e["timestamp"]):
        f.write(json.dumps(e) + "\n")

# ---------------------------------------------------------------- problems (simplified export of dt.davis.problems) for Labs 1.1 and 1.5
fails = sum(1 for r in recs if 118 <= int(r["start"] // 60) < 162 and r["failed"])
PROBLEMS = [
    {"display_id": "P-26111203", "event.name": "CPU saturation", "event.category": "RESOURCE", "event.status": "CLOSED",
     "event.start": at("03:10"), "event.end": at("03:42"), "root_cause_entity_name": "batch-01", "root_cause_entity_type": "HOST",
     "affected_entities": [{"type": "HOST", "name": "batch-01"}, {"type": "PROCESS_GROUP", "name": "report-generator"}],
     "dt.davis.affected_users_count": 0, "affected_services": [], "dt.davis.is_duplicate": False, "dt.davis.is_frequent_event": True,
     "evidence": ["CPU usage 97 % on batch-01 for 32 minutes", "report-generator nightly job running (starts 03:00 daily)"],
     "events": [{"category": "RESOURCE", "name": "CPU saturation", "entity": "batch-01"}]},
    {"display_id": "P-26111205", "event.name": "Process unavailable", "event.category": "AVAILABILITY", "event.status": "CLOSED",
     "event.start": at("09:12"), "event.end": at("09:15"), "root_cause_entity_name": "easyTravel Business Backend (app-02)", "root_cause_entity_type": "PROCESS_GROUP_INSTANCE",
     "affected_entities": [{"type": "PROCESS_GROUP_INSTANCE", "name": "easyTravel Business Backend (app-02)"}],
     "dt.davis.affected_users_count": 0, "affected_services": [], "dt.davis.is_duplicate": False, "dt.davis.is_frequent_event": False,
     "evidence": ["Process easyTravel Business Backend on app-02 exited with code 137 at 09:12:04", "easyTravel Business Backend (app-01) served all requests: failure rate 0.0 %", "systemd restarted the process at 09:14:51"],
     "events": [{"category": "AVAILABILITY", "name": "Process unavailable", "entity": "easyTravel Business Backend (app-02)"}]},
    {"display_id": "P-26111207", "event.name": "Failure rate increase", "event.category": "ERROR", "event.status": "CLOSED",
     "event.start": at("14:00", 15), "event.end": at("14:44", 30), "root_cause_entity_name": "CreditCardValidation", "root_cause_entity_type": "SERVICE",
     "affected_entities": [{"type": "SERVICE", "name": "CreditCardValidation"}, {"type": "SERVICE", "name": "BookingService"}, {"type": "SERVICE", "name": "easyTravel Customer Frontend"}],
     "dt.davis.affected_users_count": 3412, "affected_services": ["easyTravel Customer Frontend", "BookingService", "CreditCardValidation"], "dt.davis.is_duplicate": False, "dt.davis.is_frequent_event": False,
     "evidence": ["Deployment CreditCardValidation 2.8.0 at 13:58:02, 2 minutes before the problem", "Configuration change: maximum-pool-size 50 -> 10", "CreditCardValidation validateCreditCard median 2.18 s instead of 0.31 s",
                  "easyTravel Customer Frontend /orange-booking-payment.jsf failure rate 6.4 % instead of 0.1 %", f"{fails:,} bookings failed between 13:58 and 14:42"],
     "events": [{"category": "CUSTOM", "name": "CreditCardValidation connection pool: threads waiting above 5 for 2 minutes", "entity": "CreditCardValidation"},
                {"category": "SLOWDOWN", "name": "Response time degradation", "entity": "CreditCardValidation"},
                {"category": "SLOWDOWN", "name": "Response time degradation", "entity": "BookingService"},
                {"category": "ERROR", "name": "Failure rate increase", "entity": "easyTravel Customer Frontend"}]},
    {"display_id": "P-26111208", "event.name": "Failure rate increase", "event.category": "ERROR", "event.status": "CLOSED",
     "event.start": at("14:00", 40), "event.end": at("14:44", 30), "root_cause_entity_name": "CreditCardValidation", "root_cause_entity_type": "SERVICE",
     "affected_entities": [{"type": "SERVICE", "name": "easyTravel Customer Frontend"}], "dt.davis.affected_users_count": 3412, "affected_services": ["easyTravel Customer Frontend"],
     "dt.davis.is_duplicate": True, "dt.davis.is_frequent_event": False, "evidence": ["Duplicate of P-26111207"], "events": []},
    {"display_id": "P-26111211", "event.name": "Response time degradation", "event.category": "SLOWDOWN", "event.status": "ACTIVE",
     "event.start": at("16:02"), "event.end": None, "root_cause_entity_name": "web-01", "root_cause_entity_type": "HOST",
     "affected_entities": [{"type": "SERVICE", "name": "easyTravel Customer Frontend"}, {"type": "HOST", "name": "web-01"}],
     "dt.davis.affected_users_count": 860, "affected_services": ["easyTravel Customer Frontend"], "dt.davis.is_duplicate": False, "dt.davis.is_frequent_event": False,
     "evidence": ["easyTravel Customer Frontend /orange.jsf median 410 ms instead of 38 ms", "CPU usage 96 % on web-01 (4 cores), load per core 2.3", "Process image-resizer started on web-01 at 16:00:31"],
     "events": [{"category": "RESOURCE", "name": "CPU saturation", "entity": "web-01"}, {"category": "SLOWDOWN", "name": "Response time degradation", "entity": "easyTravel Customer Frontend"}]},
    {"display_id": "P-26111212", "event.name": "Bookings per minute below 600", "event.category": "CUSTOM", "event.status": "ACTIVE",
     "event.start": at("16:05"), "event.end": None, "root_cause_entity_name": None, "root_cause_entity_type": None,
     "affected_entities": [], "dt.davis.affected_users_count": 0, "affected_services": [], "dt.davis.is_duplicate": False, "dt.davis.is_frequent_event": False,
     "evidence": ["Business metric bookings.created per minute: 512 (threshold 600)", "Custom alert from a metric event on business events"],
     "events": [{"category": "CUSTOM", "name": "Bookings per minute below 600", "entity": "easyTravel"}]},
]
with open(os.path.join(OUT, "problems.json"), "w") as f:
    json.dump(PROBLEMS, f, indent=2)
