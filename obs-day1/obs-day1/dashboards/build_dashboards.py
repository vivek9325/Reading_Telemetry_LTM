#!/usr/bin/env python3
"""Write the two Dynatrace dashboard definitions (JSON) used in Labs 1.2 and 1.3.
Upload them in the Dashboards app: Upload (or Import), then pick the file."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SVC_VAR = {"version": 2, "key": "Service", "type": "query", "visible": True, "editable": True, "multiple": False,
           "input": "timeseries r = sum(dt.service.request.count), by: {dt.service.name}\n| fields dt.service.name\n| sort dt.service.name asc"}

def md(text):
    return {"type": "markdown", "content": text}

def data(title, query, viz, settings=None):
    return {"type": "data", "title": title, "query": query, "visualization": viz,
            "visualizationSettings": settings or {}, "querySettings": {}}

def thresholds(warn, crit):
    return {"thresholds": [{"id": 1, "field": "", "title": "", "isEnabled": True, "rules": [
        {"id": 0, "color": {"Default": "var(--dt-colors-charts-status-ideal-default, #2f6862)"}, "comparator": ">=", "label": "OK", "value": 0},
        {"id": 1, "color": {"Default": "var(--dt-colors-charts-status-warning-default, #eea53c)"}, "comparator": ">=", "label": "Warning", "value": warn},
        {"id": 2, "color": {"Default": "var(--dt-colors-charts-status-critical-default, #c62239)"}, "comparator": ">=", "label": "Critical", "value": crit}]}]}

def dashboard(name, variables, tiles, layouts):
    return {"name": name, "type": "dashboard", "content": {"version": 21, "variables": variables,
            "tiles": {str(i): t for i, t in enumerate(tiles)}, "layouts": {str(i): l for i, l in enumerate(layouts)}}}

F = "filter: {dt.service.name == $Service}"
red = dashboard("easyTravel - RED for one service (Lab 1.2)", [SVC_VAR], [
    md("# RED: rate, errors, duration\nPick a service at the top. Response times are converted from microseconds to milliseconds."),
    data("Rate: requests per minute", f"timeseries requests_per_min = sum(dt.service.request.count, rate: 1m), {F}", "lineChart"),
    data("Errors: failure rate (%)", f"timeseries {{requests = sum(dt.service.request.count), failures = sum(dt.service.request.failure_count)}}, {F}\n| fieldsAdd failure_rate_pct = failures[] * 100.0 / requests[]\n| fieldsRemove requests, failures", "lineChart", thresholds(1, 5)),
    data("Duration: response time percentiles (ms)", f"timeseries {{p50 = percentile(dt.service.request.response_time, 50), p95 = percentile(dt.service.request.response_time, 95), p99 = percentile(dt.service.request.response_time, 99)}}, {F}\n| fieldsAdd p50_ms = p50[] / 1000, p95_ms = p95[] / 1000, p99_ms = p99[] / 1000\n| fieldsRemove p50, p95, p99", "lineChart", thresholds(500, 1000)),
    data("Endpoints of the service", "fetch spans\n| filter request.is_root_span == true and dt.service.name == $Service\n| summarize {requests = count(), failures = countIf(request.is_failed == true), p95 = percentile(duration, 95)}, by: {endpoint.name}\n| fieldsAdd failure_rate_pct = failures * 100.0 / requests\n| sort p95 desc", "table"),
], [{"x": 0, "y": 0, "w": 24, "h": 2}, {"x": 0, "y": 2, "w": 12, "h": 6}, {"x": 12, "y": 2, "w": 12, "h": 6},
    {"x": 0, "y": 8, "w": 24, "h": 7}, {"x": 0, "y": 15, "w": 24, "h": 5}])

ops = dashboard("easyTravel - Operations (Lab 1.3)", [SVC_VAR], [
    md("# easyTravel operations\nTop row: is anything wrong now? Middle: since when, and where? Bottom: detail for the service picked at the top."),
    data("Bookings per minute", "timeseries r = sum(dt.service.request.count, rate: 1m), filter: {dt.service.name == \"BookingService\"}\n| fieldsAdd requests_per_min = arrayAvg(r)\n| fields requests_per_min, r", "singleValue"),
    data("Failure rate, all services (%)", "timeseries {r = sum(dt.service.request.count), f = sum(dt.service.request.failure_count)}\n| fieldsAdd failure_rate_pct = arraySum(f) * 100.0 / arraySum(r)\n| fields failure_rate_pct", "singleValue", thresholds(1, 5)),
    data("Active problems", "fetch dt.davis.problems\n| filter not(dt.davis.is_duplicate) and event.status == \"ACTIVE\"\n| summarize active_problems = count()", "singleValue"),
    data("p95 response time by service (ms)", "timeseries p95 = percentile(dt.service.request.response_time, 95), by: {dt.service.name}\n| fieldsAdd p95_ms = p95[] / 1000\n| fieldsRemove p95", "lineChart"),
    data("Failure rate by service (%)", "timeseries {r = sum(dt.service.request.count), f = sum(dt.service.request.failure_count)}, by: {dt.service.name}\n| fieldsAdd failure_rate_pct = f[] * 100.0 / r[]\n| fieldsRemove r, f", "lineChart", thresholds(1, 5)),
    data("Requests per minute by service", "timeseries requests_per_min = sum(dt.service.request.count, rate: 1m), by: {dt.service.name}", "barChart"),
    data("Response time distribution (selected service)", "fetch spans\n| filter request.is_root_span == true and dt.service.name == $Service\n| summarize requests = count(), by: {minute = toString(bin(start_time, 1m)), latency = range(duration, 100ms)}", "heatmap"),
    data("Endpoints by p95 (selected service)", "fetch spans\n| filter request.is_root_span == true and dt.service.name == $Service\n| summarize {requests = count(), failures = countIf(request.is_failed == true), p95 = percentile(duration, 95)}, by: {endpoint.name}\n| sort p95 desc", "table"),
    data("Host CPU usage now (%)", "timeseries cpu = avg(dt.host.cpu.usage), by: {dt.smartscape.host}\n| fieldsAdd host = getNodeName(dt.smartscape.host), cpu_now = arrayLast(cpu)\n| fields host, cpu_now", "honeycomb", thresholds(80, 95)),
    data("Lab VM memory used (%)", "timeseries m = avg(dt.host.memory.usage)\n| fields memory_used_pct = arrayLast(m)", "gauge", {"minValue": 0, "maxValue": 100}),
    data("Problems in the time frame", "fetch dt.davis.problems\n| filter not(dt.davis.is_duplicate)\n| fields event.start, display_id, event.name, event.category, event.status\n| sort event.start desc", "table"),
], [{"x": 0, "y": 0, "w": 24, "h": 2},
    {"x": 0, "y": 2, "w": 8, "h": 4}, {"x": 8, "y": 2, "w": 8, "h": 4}, {"x": 16, "y": 2, "w": 8, "h": 4},
    {"x": 0, "y": 6, "w": 12, "h": 6}, {"x": 12, "y": 6, "w": 12, "h": 6}, {"x": 0, "y": 12, "w": 24, "h": 5},
    {"x": 0, "y": 17, "w": 12, "h": 7}, {"x": 12, "y": 17, "w": 12, "h": 7},
    {"x": 0, "y": 24, "w": 8, "h": 5}, {"x": 8, "y": 24, "w": 6, "h": 5}, {"x": 14, "y": 24, "w": 10, "h": 5}])

(HERE / "easytravel-red.json").write_text(json.dumps(red, indent=2) + "\n")
(HERE / "easytravel-operations.json").write_text(json.dumps(ops, indent=2) + "\n")
print("wrote easytravel-red.json and easytravel-operations.json")
