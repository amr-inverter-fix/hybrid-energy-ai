"""Telemetry schema and validation. Pure Python, no framework, so it is reusable and testable.

Required: device_id, timestamp, source. All sensor fields are optional; a missing one is
reported as 'missing', never filled in. Units are fixed (see FIELDS)."""
import math
from datetime import datetime, timezone, timedelta

SCHEMA_VERSION = "1.0"
# name: (unit, min, max, description). Ranges are plausibility limits for a 12 V / 600 W system
# (assumed; edit with real datasheet values). Out of range => packet rejected.
FIELDS = {
    "v_batt":   ("V",    0.0,   30.0,  "battery terminal voltage"),
    "i_batt":   ("A",  -100.0, 100.0,  "battery current, + = charging"),
    "soc":      ("%",    0.0,  100.0,  "state of charge reported by the device"),
    "pv_w":     ("W",    0.0, 2000.0,  "PV power"),
    "g_wm2":    ("W/m2", 0.0, 1500.0,  "irradiance"),
    "wind_ms":  ("m/s",  0.0,   60.0,  "wind speed"),
    "wind_w":   ("W",    0.0, 1000.0,  "wind turbine power"),
    "load_w":   ("W",    0.0, 5000.0,  "load power"),
    "t_batt_c": ("C",  -40.0,  100.0,  "battery temperature"),
}
SOURCES = ("device", "simulation", "replay")
MAX_FUTURE = timedelta(minutes=5)
MAX_AGE = timedelta(hours=24)


class ValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def parse_timestamp(ts):
    if not isinstance(ts, str):
        raise ValueError("timestamp must be an ISO-8601 string with timezone")
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("timestamp is not ISO-8601")
    if d.tzinfo is None:
        raise ValueError("timestamp must include a timezone (use Z or +hh:mm)")
    return d.astimezone(timezone.utc)


def validate(payload, now=None, check_age=True):
    """Return a normalized dict or raise ValidationError. Never coerces strings to numbers."""
    now = now or datetime.now(timezone.utc)
    errs = []
    if not isinstance(payload, dict):
        raise ValidationError(["payload must be a JSON object"])
    allowed = {"device_id", "timestamp", "source"} | set(FIELDS)
    extra = sorted(set(payload) - allowed)
    if extra:
        errs.append("unknown fields: " + ",".join(extra[:5]))
    did = payload.get("device_id")
    if not isinstance(did, str) or not (1 <= len(did) <= 64) or not all(c.isalnum() or c in "-_." for c in did):
        errs.append("device_id must be 1-64 chars [A-Za-z0-9._-]")
    src = payload.get("source")
    if src not in SOURCES:
        errs.append("source must be one of " + "/".join(SOURCES))
    ts = None
    try:
        ts = parse_timestamp(payload.get("timestamp"))
        if ts - now > MAX_FUTURE:
            errs.append("timestamp is in the future")
        if check_age and now - ts > MAX_AGE:
            errs.append("timestamp older than 24 h")
    except ValueError as e:
        errs.append(str(e))
    vals, status = {}, {}
    for k, (unit, lo, hi, _) in FIELDS.items():
        if k not in payload or payload[k] is None:
            status[k] = "missing"
            continue
        v = payload[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            errs.append(f"{k} must be a finite number ({unit})")
            continue
        if v < lo or v > hi:
            errs.append(f"{k}={v} outside plausible range [{lo},{hi}] {unit}")
            continue
        vals[k] = float(v)
        status[k] = "ok"
    if not vals and not errs:
        errs.append("no sensor values present")
    if errs:
        raise ValidationError(errs)
    return {"device_id": did, "timestamp": ts.isoformat(), "source": src, "values": vals, "status": status,
            "schema_version": SCHEMA_VERSION}
