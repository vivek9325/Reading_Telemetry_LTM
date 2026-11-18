#!/usr/bin/env python3
"""Render the sample problem cards in incident/problems.json as one HTML page (cards/problem-cards.html).
Open the page in a browser; print it to PDF if you want paper copies for Lab 1.5."""
import html, json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
COL = {"AVAILABILITY": "#c62239", "ERROR": "#c62239", "SLOWDOWN": "#d97706", "RESOURCE": "#d97706", "CUSTOM": "#6d28d9", "INFO": "#475569"}
def hm(t):
    return t[11:16] if t else ""
def dur(a, b):
    if not b:
        return "Active, still open at 16:30"
    m = (datetime.fromisoformat(b.replace("Z", "+00:00")) - datetime.fromisoformat(a.replace("Z", "+00:00"))).seconds // 60
    return f"Closed after {m} min"
cards = []
for p in json.loads((BASE / "incident" / "problems.json").read_text()):
    if p["dt.davis.is_duplicate"]:
        continue
    c = COL[p["event.category"]]
    ents = ", ".join(f"{html.escape(e['name'])} <span class='t'>({e['type'].replace('_', ' ').lower()})</span>" for e in p["affected_entities"]) or "none recorded"
    rc = (f"<div class='rc'><b>{html.escape(p['root_cause_entity_name'])}</b> <span class='t'>({p['root_cause_entity_type'].replace('_', ' ').lower()})</span></div>"
          if p["root_cause_entity_name"] else "<div class='rc none'>No root cause entity identified</div>")
    ev = "".join(f"<li><span class='chip' style='--c:{COL[e['category']]}'>{e['category'].title()}</span>{html.escape(e['name'])} <span class='t'>on {html.escape(e['entity'])}</span></li>" for e in p["events"])
    evid = "".join(f"<li>{html.escape(x)}</li>" for x in p["evidence"])
    flags = " <span class='flag'>frequent issue</span>" if p["dt.davis.is_frequent_event"] else ""
    cards.append(f"""<section class='card' id='{p['display_id']}'>
<div class='top'><div><div class='id'>{p['display_id']} &middot; 12 Nov 2026, opened {hm(p['event.start'])} UTC</div><h2>{html.escape(p['event.name'])}</h2></div>
<div class='st'><span class='chip big' style='--c:{c}'>{p['event.category'].title()}</span><div class='t'>{dur(p['event.start'], p['event.end'])}</div></div></div>
<h3>Impact</h3><p><b>{p['dt.davis.affected_users_count']:,}</b> affected users &middot; affected: {ents}{flags}</p>
<h3>Root cause</h3>{rc}<ul class='ev'>{evid}</ul>
<h3>Events</h3><ul class='evs'>{ev}</ul></section>""")
page = f"""<!doctype html><html><head><meta charset='utf-8'><title>easyTravel sample problem cards</title><style>
body{{font:14px/1.45 system-ui,-apple-system,'Segoe UI',sans-serif;background:#f1f3f6;color:#1b2430;margin:0;padding:24px}}
h1{{font-size:18px;margin:0 0 4px}} .sub{{color:#5b6573;margin:0 0 20px}}
.card{{background:#fff;border:1px solid #d5dae1;border-radius:10px;padding:18px 22px;margin:0 0 18px;max-width:880px}}
.top{{display:flex;justify-content:space-between;gap:16px}} .id{{color:#5b6573;font-size:12.5px}} h2{{margin:2px 0 0;font-size:19px}}
.st{{text-align:right}} h3{{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:#5b6573;margin:16px 0 6px}}
p{{margin:0}} .t{{color:#5b6573}} .chip{{display:inline-block;border:1px solid var(--c);color:var(--c);background:color-mix(in srgb,var(--c) 10%,white);border-radius:999px;padding:0 9px;font-size:12px;font-weight:600;margin-right:8px}}
.chip.big{{font-size:13px;padding:2px 12px;margin:0 0 6px}} .rc{{background:#f1f3f6;border-radius:6px;padding:8px 12px}} .rc.none{{color:#5b6573;font-style:italic}}
ul{{margin:6px 0 0;padding-left:20px}} .evs{{list-style:none;padding:0}} .evs li{{margin:4px 0}} .flag{{background:#fff3d6;border-radius:4px;padding:0 6px;font-size:12px;margin-left:6px}}
</style></head><body><h1>easyTravel: sample problem cards, 12 November 2026</h1><p class='sub'>Training material for Lab 1.5. Simplified from the fields of dt.davis.problems; all data is invented.</p>{''.join(cards)}</body></html>"""
(BASE / "cards" / "problem-cards.html").write_text(page)
print("wrote cards/problem-cards.html with", len(cards), "cards")
