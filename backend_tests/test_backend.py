import json, unittest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from backend.app import create_app, Config
from backend.schema import validate, ValidationError
from backend.adapters import MqttBridge, ModbusMap
from backend.security import RateLimiter

ADMIN, VIEW = "admin-key-test", "viewer-key-test"
def iso(dt=None): return (dt or datetime.now(timezone.utc)).isoformat()
def pkt(dev="esp32-01", ts=None, **kw):
    d = {"device_id": dev, "timestamp": ts or iso(), "source": "device", "v_batt": 12.6, "soc": 80.0, "pv_w": 120.0}
    d.update(kw); return d

class SchemaTests(unittest.TestCase):
    def test_valid_with_missing_optional(self):
        r = validate(pkt())
        self.assertEqual(r["status"]["i_batt"], "missing"); self.assertNotIn("i_batt", r["values"])
    def test_rejects(self):
        bad = [pkt(v_batt=99), pkt(v_batt="12"), pkt(v_batt=float("nan")), pkt(v_batt=True), pkt(extra=1),
               pkt(source="x"), pkt(dev="bad id!"), pkt(ts="2020-01-01T00:00:00"), pkt(ts="yesterday"),
               pkt(ts=iso(datetime.now(timezone.utc)+timedelta(hours=1))), pkt(ts=iso(datetime.now(timezone.utc)-timedelta(days=2))),
               {"device_id": "a", "timestamp": iso(), "source": "device"}, "str", [1], pkt(soc=-1), pkt(wind_ms=-0.1)]
        for b in bad:
            with self.assertRaises(ValidationError, msg=str(b)[:60]): validate(b)

def client(**kw):
    kw.setdefault('burst', 1000)
    app = create_app(Config(admin_key=ADMIN, viewer_key=VIEW, **kw)); return TestClient(app), app
def H(k): return {"x-api-key": k}
def register(c, dev="esp32-01", **kw):
    r = c.post("/api/v1/devices", json={"device_id": dev, **kw}, headers=H(ADMIN)); return r

class ApiTests(unittest.TestCase):
    def test_auth_and_roles(self):
        c, _ = client()
        self.assertEqual(c.get("/api/v1/devices").status_code, 401)
        self.assertEqual(c.get("/api/v1/devices", headers=H("wrong")).status_code, 401)
        self.assertEqual(c.get("/api/v1/devices", headers=H(VIEW)).status_code, 200)
        self.assertEqual(c.post("/api/v1/devices", json={"device_id": "a"}, headers=H(VIEW)).status_code, 403)
        self.assertEqual(c.post("/api/v1/telemetry", json=pkt(), headers=H(ADMIN)).status_code, 403)  # admin is not a device
    def test_no_keys_configured_refuses(self):
        c = TestClient(create_app(Config()))
        self.assertEqual(c.get("/api/v1/devices", headers=H("x")).status_code, 503)
    def test_register_ingest_duplicate_and_history(self):
        c, _ = client(); r = register(c, heartbeat_s=60); self.assertEqual(r.status_code, 201)
        key = r.json()["api_key"]; self.assertEqual(register(c).status_code, 409)
        p = pkt(); r1 = c.post("/api/v1/telemetry", json=p, headers=H(key)); self.assertEqual(r1.status_code, 201)
        r2 = c.post("/api/v1/telemetry", json=p, headers=H(key)); self.assertEqual(r2.json()["result"], "duplicate")
        h = c.get("/api/v1/devices/esp32-01/history", headers=H(VIEW)).json(); self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["status"]["i_batt"], "missing")
        ev = [e["kind"] for e in c.get("/api/v1/devices/esp32-01/events", headers=H(VIEW)).json()]
        self.assertIn("duplicate", ev); self.assertIn("registered", ev)
    def test_invalid_packet_rejected_and_logged(self):
        c, _ = client(); key = register(c).json()["api_key"]
        r = c.post("/api/v1/telemetry", json=pkt(v_batt=500), headers=H(key)); self.assertEqual(r.status_code, 422)
        self.assertEqual(c.post("/api/v1/telemetry", data="not json", headers=H(key)).status_code, 400)
        self.assertEqual(c.get("/api/v1/devices/esp32-01/history", headers=H(VIEW)).json(), [])
        self.assertEqual(c.get("/api/v1/devices/esp32-01/live-status", headers=H(VIEW)).json()["rejected_packets"], 1)
    def test_device_cannot_write_for_another_device(self):
        c, _ = client(); k1 = register(c, "dev-a").json()["api_key"]; register(c, "dev-b")
        r = c.post("/api/v1/telemetry", json=pkt("dev-b"), headers=H(k1)); self.assertEqual(r.status_code, 403)
    def test_unregistered_device(self):
        c, app = client(); k = register(c, "dev-a").json()["api_key"]
        out, _ = app.state.service.ingest(pkt("ghost")); self.assertEqual(out, "unknown_device")
    def test_size_limit(self):
        c, _ = client(); k = register(c).json()["api_key"]
        r = c.post("/api/v1/telemetry", content=b"{" + b" " * 5000 + b"}", headers={**H(k), "content-type": "application/json"})
        self.assertEqual(r.status_code, 413)
    def test_rate_limit(self):
        c, _ = client(rate_per_s=0.0001, burst=3)
        codes = [c.get("/api/v1/health").status_code for _ in range(6)]
        self.assertEqual(codes[:3], [200] * 3); self.assertIn(429, codes[3:])
    def test_simulated_telemetry_never_enables_live(self):
        c, app = client(); k = register(c).json()["api_key"]
        base = datetime.now(timezone.utc)
        for i in range(30):
            r = c.post("/api/v1/telemetry", json=pkt(ts=iso(base - timedelta(seconds=i)), source="simulation"), headers=H(k)); self.assertEqual(r.status_code, 201)
        st = c.get("/api/v1/devices/esp32-01/live-status", headers=H(VIEW)).json()
        self.assertFalse(st["live_verified"]); self.assertEqual(st["valid_device_packets"], 0)
    def test_live_requires_ten_device_packets_and_online(self):
        c, app = client(); k = register(c).json()["api_key"]; base = datetime.now(timezone.utc)
        for i in range(9): c.post("/api/v1/telemetry", json=pkt(ts=iso(base - timedelta(seconds=i))), headers=H(k))
        self.assertFalse(c.get("/api/v1/devices/esp32-01/live-status", headers=H(VIEW)).json()["live_verified"])
        c.post("/api/v1/telemetry", json=pkt(ts=iso(base - timedelta(seconds=20))), headers=H(k))
        self.assertTrue(c.get("/api/v1/devices/esp32-01/live-status", headers=H(VIEW)).json()["live_verified"])
        # offline: pretend last_seen is old
        app.state.store.q("update devices set last_seen=? where device_id='esp32-01'", (iso(base - timedelta(hours=1)),), write=True)
        st = c.get("/api/v1/devices/esp32-01/live-status", headers=H(VIEW)).json()
        self.assertFalse(st["live_verified"]); self.assertEqual(st["status"], "offline")
    def test_registration_validation(self):
        c, _ = client()
        for b in [{"device_id": "bad id"}, {"device_id": "a", "heartbeat_s": 1}, {"device_id": "a", "sensor_map": {"nope": 1}}, {}]:
            self.assertEqual(c.post("/api/v1/devices", json=b, headers=H(ADMIN)).status_code, 422)
    def test_key_never_returned_after_registration(self):
        c, _ = client(); register(c)
        self.assertNotIn("key", json.dumps(c.get("/api/v1/devices", headers=H(VIEW)).json()).replace("heartbeat", ""))
    def test_websocket_auth_and_broadcast(self):
        c, app = client(); k = register(c).json()["api_key"]
        with self.assertRaises(Exception):
            with c.websocket_connect("/ws/telemetry"): pass
        with TestClient(app) as c2, c2.websocket_connect("/ws/telemetry?token=" + VIEW) as ws:
            c2.post("/api/v1/telemetry", json=pkt(), headers=H(k))
            msg = json.loads(ws.receive_text()); self.assertEqual(msg["device_id"], "esp32-01")
    def test_schema_endpoint(self):
        c, _ = client(); s = c.get("/api/v1/schema").json(); self.assertIn("t_batt_c", s["fields"])

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.c, self.app = client(); self.k = register(self.c).json()["api_key"]
        self.br = MqttBridge(self.app.state.service)
    def test_mqtt_ok_and_dup(self):
        p = json.dumps(pkt()).encode()
        self.assertEqual(self.br.on_message("hybrid/esp32-01/telemetry", p)[0], "stored")
        self.assertEqual(self.br.on_message("hybrid/esp32-01/telemetry", p)[0], "duplicate")
    def test_mqtt_rejections(self):
        for topic, p in [("hybrid/esp32-01/telemetry", b"{bad"), ("hybrid/other/telemetry", json.dumps(pkt()).encode()),
                         ("x/y", b"{}"), ("hybrid/esp32-01/telemetry", b"x" * 5000),
                         ("hybrid/esp32-01/telemetry", json.dumps(pkt(v_batt=-5)).encode())]:
            self.assertEqual(self.br.on_message(topic, p)[0], "rejected")
    def test_modbus_decode(self):
        m = ModbusMap("esp32-01", {"v_batt": (0, 0.01, False), "i_batt": (1, 0.1, True)})
        d = m.decode({0: 1260, 1: 0xFFF6}, iso())
        self.assertAlmostEqual(d["v_batt"], 12.6); self.assertAlmostEqual(d["i_batt"], -1.0)
        d2 = m.decode({0: 1260}, iso()); self.assertNotIn("i_batt", d2)
        self.assertEqual(self.app.state.service.ingest(d2, "esp32-01", via="modbus")[0], "stored")
        with self.assertRaises(ValueError): ModbusMap("a", {"bogus": (0, 1, False)})
    def test_rate_limiter_refills(self):
        t = [0.0]; rl = RateLimiter(1.0, 2, clock=lambda: t[0])
        self.assertTrue(rl.allow("a") and rl.allow("a")); self.assertFalse(rl.allow("a")); t[0] = 1.5; self.assertTrue(rl.allow("a"))

if __name__ == "__main__": unittest.main()
