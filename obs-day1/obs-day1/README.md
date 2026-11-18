# obs-day1: lab pack for Day 1, Observability Foundations & Incident Triage (Dynatrace + easyTravel)

The files for the five Day 1 labs. The Lab Guide tells you which ones to use and when.
The live labs (1.2 to 1.4) use **Dynatrace easyTravel**, the Dynatrace demo application, installed on
a Linux VM and monitored by OneAgent. Labs 1.1 and 1.5 use the offline incident bundle in `incident/`.

## Setup (Ubuntu VM, 4 vCPU and 8 GB RAM or more)

```bash
sudo apt update && sudo apt install -y openjdk-11-jre-headless jq stress-ng unzip python3
unzip -o obs-day1.zip -d ~
```

Then install easyTravel and OneAgent as described in the Lab Guide ("Before you start"):

- easyTravel: `java -jar dynatrace-easytravel-linux-x86_64.jar`, then `sudo /bin/bash resources/installChromeDeps.sh`
  in the install folder, then `weblauncher/weblauncher.sh`. The Web Launcher is on port 8094; the shop on port 8079.
- OneAgent: full-stack, from your Dynatrace environment (Deploy OneAgent). Exclude the launcher and weblauncher
  processes from monitoring.

easyTravel is no longer maintained by Dynatrace (it is deprecated in favour of easyTrade), but it still installs
and runs on Ubuntu 20.04/22.04 for training.

## What is in the pack

| Path | What it is | Lab |
| --- | --- | --- |
| `incident/` | The 12 November booking incident in an easyTravel production setup: service, host and pool metrics, events, logs, spans and problems. Invented data. | 1.1, 1.4, 1.5 |
| `bin/window.py`, `bin/series.py`, `bin/waterfall.py` | Read the incident files: RED summary for a window, per-minute bars, a trace waterfall. | 1.1, 1.4 |
| `bin/check.py` | Checks the Web Launcher (8094), the shop (8079), the Business Backend (8091) and the OneAgent service. | 1.2 |
| `bin/pattern.py` | Turns easyTravel problem patterns on and off through the Business Backend. | 1.2 to 1.4 |
| `bin/scenario.py` | Timed problem-pattern scenarios: `lab12` (12 minutes) and `lab13` (20 minutes). | 1.2 to 1.4 |
| `dashboards/` | Dashboard JSON to upload: `easytravel-red.json` (the Lab 1.2 answer) and `easytravel-operations.json` (Lab 1.3). `build_dashboards.py` rebuilds them. | 1.2, 1.3 |
| `cards/problem-cards.html` | The five sample problem cards, to open in a browser. | 1.5 |
| `make_incident.py` | Rebuilds `incident/` from a fixed seed (same files every time). | instructor |

The helper scripts use only the Python standard library. Set `ET_HOST=<address>` if easyTravel runs on another machine.

## Problem patterns used

| Pattern | Effect | Lab |
| --- | --- | --- |
| `CreditCardCheckError500` | BookingService cannot reach the credit card check: bookings fail | 1.2, 1.3, 1.4 |
| `CPULoadJourneyService` | CPU-heavy work in JourneyService: journey search and its callers slow down | 1.3, 1.4 |
| `CPULoad` | High CPU in the Business Backend process | 1.2 (USE) |

## Notes

- All host names, IP addresses, users and IDs in `incident/` are invented (`example.com`, documentation address ranges).
- Times in `incident/` are UTC.
- Clean up: `bin/pattern.py reset`, stop easyTravel in the Web Launcher, and remove the VM from Dynatrace if it was temporary.
