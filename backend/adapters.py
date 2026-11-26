"""MQTT and Modbus adapters. Both only feed Service.ingest, so they share validation, dedup and live rules.
STATUS: unit-tested with mocks. NOT tested against a real broker or a real Modbus device."""
import json, struct
from .schema import FIELDS


class MqttBridge:
    """Subscribes to hybrid/<device_id>/telemetry. Broker credentials come from environment variables,
    never from code or the frontend. The topic's device_id must equal the payload's device_id."""
    TOPIC = "hybrid/+/telemetry"

    def __init__(self, service, host=None, port=1883, username=None, password=None, tls=False, client=None):
        self.service, self.host, self.port = service, host, port
        self.username, self.password, self.tls = username, password, tls
        self._client = client

    def on_message(self, topic: str, payload: bytes):
        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != "hybrid" or parts[2] != "telemetry":
            return ("rejected", ["bad topic"])
        if len(payload) > 4096:
            self.service.store.event("rejected", parts[1][:64], "mqtt: payload too large")
            return ("rejected", ["payload too large"])
        try:
            data = json.loads(payload)
        except Exception:
            self.service.store.event("rejected", parts[1][:64], "mqtt: invalid JSON")
            return ("rejected", ["invalid JSON"])
        if not isinstance(data, dict) or data.get("device_id") != parts[1]:
            self.service.store.event("rejected", parts[1][:64], "mqtt: topic/device_id mismatch")
            return ("rejected", ["topic device_id does not match payload device_id"])
        return self.service.ingest(data, authenticated_device=parts[1], via="mqtt")

    def start(self):  # pragma: no cover - needs a broker
        import paho.mqtt.client as mqtt
        c = self._client or mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if self.username:
            c.username_pw_set(self.username, self.password)
        if self.tls:
            c.tls_set()
        c.on_connect = lambda cl, ud, fl, rc, pr=None: cl.subscribe(self.TOPIC, qos=1)  # re-subscribes after reconnect
        c.on_message = lambda cl, ud, m: self.on_message(m.topic, m.payload)
        c.reconnect_delay_set(1, 60)
        c.connect_async(self.host, self.port, keepalive=30)
        c.loop_start()
        self._client = c


class ModbusMap:
    """Register map: field -> (address, scale, signed, count). Raw 16-bit holding registers.
    Example: v_batt at 0 with scale 0.01 means raw 1250 -> 12.50 V."""
    def __init__(self, device_id, regs):
        for k in regs:
            if k not in FIELDS:
                raise ValueError(f"unknown field {k}")
        self.device_id, self.regs = device_id, regs

    def decode(self, registers: dict, timestamp_iso: str):
        """registers: {address: raw_u16}. Fields whose registers were not read are omitted (reported missing)."""
        out = {"device_id": self.device_id, "timestamp": timestamp_iso, "source": "device"}
        for k, (addr, scale, signed) in self.regs.items():
            if addr not in registers:
                continue
            raw = registers[addr] & 0xFFFF
            if signed and raw >= 0x8000:
                raw -= 0x10000
            out[k] = raw * scale
        return out


class ModbusPoller:  # pragma: no cover - needs a device
    def __init__(self, service, mapping: ModbusMap, host, port=502, unit=1):
        self.service, self.map, self.host, self.port, self.unit = service, mapping, host, port, unit

    def poll_once(self, now_iso):
        from pymodbus.client import ModbusTcpClient
        c = ModbusTcpClient(self.host, port=self.port, timeout=3)
        try:
            if not c.connect():
                self.service.store.event("connection_error", self.map.device_id, "modbus connect failed")
                return ("rejected", ["connect failed"])
            regs = {}
            for k, (addr, _, _) in self.map.regs.items():
                r = c.read_holding_registers(addr, count=1, slave=self.unit)
                if not r.isError():
                    regs[addr] = r.registers[0]
            return self.service.ingest(self.map.decode(regs, now_iso), authenticated_device=self.map.device_id, via="modbus")
        finally:
            c.close()
