"""Shared settings for the easyTravel helper scripts (standard library only).

Set ET_HOST if easyTravel runs on another machine (default: localhost).
"""
import os, urllib.error, urllib.parse, urllib.request

HOST = os.environ.get("ET_HOST", "localhost")
BACKEND = f"http://{HOST}:{os.environ.get('ET_BACKEND_PORT', '8091')}"
FRONTEND = f"http://{HOST}:{os.environ.get('ET_FRONTEND_PORT', '8079')}"
LAUNCHER = f"http://{HOST}:{os.environ.get('ET_LAUNCHER_PORT', '8094')}"

# The problem patterns this course uses, and what each one does.
PATTERNS = {
    "CPULoadJourneyService": "CPU-heavy work in JourneyService (checkDestination): slows journey search and the services that call it",
    "CreditCardCheckError500": "BookingService cannot reach the credit card check: bookings fail with HTTP 500",
    "CPULoad": "high CPU usage in the Business Backend process (host CPU, USE)",
}


def get(url, timeout=10):
    """Return (HTTP status, seconds) for a GET; status 0 means no answer."""
    import time
    t = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read()
            return r.status, time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, time.time() - t
    except Exception:
        return 0, time.time() - t


def set_pattern(name, enabled):
    """Enable or disable one problem pattern through the Business Backend's ConfigurationService."""
    q = urllib.parse.urlencode({"name": name, "enabled": "true" if enabled else "false"})
    status, _ = get(f"{BACKEND}/services/ConfigurationService/setPluginEnabled?{q}")
    return status
