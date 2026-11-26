"""Ingestion service shared by REST, MQTT and Modbus paths. One validation path for all."""
from datetime import datetime, timezone
from .schema import validate, ValidationError
from .store import Store, online_status

LIVE_MIN_PACKETS = 10


class Service:
    def __init__(self, store: Store, publish=None):
        self.store = store
        self.publish = publish or (lambda rec: None)

    def ingest(self, payload, authenticated_device=None, via="rest", now=None):
        """Returns (outcome, detail). outcome in stored|duplicate|rejected|unknown_device|forbidden."""
        try:
            rec = validate(payload, now=now)
        except ValidationError as e:
            did = payload.get("device_id") if isinstance(payload, dict) and isinstance(payload.get("device_id"), str) else authenticated_device
            self.store.event("rejected", (did or "")[:64] or None, f"{via}: {e}")
            return "rejected", e.errors
        dev = self.store.device(rec["device_id"])
        if dev is None:
            self.store.event("unknown_device", rec["device_id"], f"{via}: device not registered")
            return "unknown_device", ["device not registered"]
        if authenticated_device is not None and authenticated_device != rec["device_id"]:
            self.store.event("forbidden", authenticated_device, f"{via}: credential used for {rec['device_id']}")
            return "forbidden", ["credential does not belong to this device_id"]
        if not self.store.insert_telemetry(rec):
            self.store.event("duplicate", rec["device_id"], rec["timestamp"])
            return "duplicate", ["same device_id and timestamp already stored"]
        self.publish(rec)
        return "stored", rec

    def live_status(self, device_id, now=None):
        """Live mode may be enabled only if ALL hold; each reason is returned so the UI can show why not."""
        dev = self.store.device(device_id)
        if not dev:
            return {"live_verified": False, "reasons": ["device not registered"]}
        reasons = []
        n = self.store.count(device_id, "device")
        if n < LIVE_MIN_PACKETS:
            reasons.append(f"only {n} valid source=device packets, need {LIVE_MIN_PACKETS}")
        st = online_status(dev, now)
        if st != "online":
            reasons.append(f"device status is {st}")
        return {"live_verified": not reasons, "reasons": reasons, "valid_device_packets": n,
                "rejected_packets": self.store.count_events(device_id, "rejected"), "status": st}
