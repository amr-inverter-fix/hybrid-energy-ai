import json, sqlite3, threading
from datetime import datetime, timezone, timedelta


class Store:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript("""
            create table if not exists devices(device_id text primary key, key_hash text not null, name text,
              heartbeat_s integer not null default 60, created text not null, sensor_map text not null default '{}', last_seen text);
            create table if not exists telemetry(id integer primary key, device_id text not null, ts text not null,
              source text not null, values_json text not null, status_json text not null, received text not null,
              unique(device_id, ts));
            create table if not exists events(id integer primary key, ts text not null, device_id text, kind text not null, detail text);
            create index if not exists tel_dev_ts on telemetry(device_id, ts);
            """)

    def q(self, sql, args=(), one=False, write=False):
        with self.lock:
            cur = self.db.execute(sql, args)
            if write:
                self.db.commit()
            rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows

    def event(self, kind, device_id=None, detail=""):
        self.q("insert into events(ts,device_id,kind,detail) values(?,?,?,?)",
               (datetime.now(timezone.utc).isoformat(), device_id, kind, detail[:500]), write=True)

    def add_device(self, device_id, key_hash, name, heartbeat_s, sensor_map):
        self.q("insert into devices(device_id,key_hash,name,heartbeat_s,created,sensor_map) values(?,?,?,?,?,?)",
               (device_id, key_hash, name, heartbeat_s, datetime.now(timezone.utc).isoformat(), json.dumps(sensor_map)), write=True)

    def device(self, device_id):
        r = self.q("select device_id,key_hash,name,heartbeat_s,created,sensor_map,last_seen from devices where device_id=?", (device_id,), one=True)
        if not r:
            return None
        return dict(zip(["device_id", "key_hash", "name", "heartbeat_s", "created", "sensor_map", "last_seen"], r))

    def devices(self):
        return [self.device(r[0]) for r in self.q("select device_id from devices order by device_id")]

    def insert_telemetry(self, rec):
        """Return True if stored, False if duplicate (same device_id + timestamp)."""
        try:
            self.q("insert into telemetry(device_id,ts,source,values_json,status_json,received) values(?,?,?,?,?,?)",
                   (rec["device_id"], rec["timestamp"], rec["source"], json.dumps(rec["values"]), json.dumps(rec["status"]),
                    datetime.now(timezone.utc).isoformat()), write=True)
        except sqlite3.IntegrityError:
            return False
        self.q("update devices set last_seen=? where device_id=?", (datetime.now(timezone.utc).isoformat(), rec["device_id"]), write=True)
        return True

    def history(self, device_id, limit=500, source=None):
        sql = "select ts,source,values_json,status_json from telemetry where device_id=?"
        a = [device_id]
        if source:
            sql += " and source=?"; a.append(source)
        sql += " order by ts desc limit ?"; a.append(min(limit, 5000))
        return [{"timestamp": r[0], "source": r[1], "values": json.loads(r[2]), "status": json.loads(r[3])} for r in self.q(sql, a)]

    def count(self, device_id, source):
        return self.q("select count(*) from telemetry where device_id=? and source=?", (device_id, source), one=True)[0]

    def events_for(self, device_id=None, limit=200):
        if device_id:
            rows = self.q("select ts,device_id,kind,detail from events where device_id=? order by id desc limit ?", (device_id, limit))
        else:
            rows = self.q("select ts,device_id,kind,detail from events order by id desc limit ?", (limit,))
        return [dict(zip(["ts", "device_id", "kind", "detail"], r)) for r in rows]

    def count_events(self, device_id, kind):
        return self.q("select count(*) from events where device_id=? and kind=?", (device_id, kind), one=True)[0]


def online_status(dev, now=None):
    now = now or datetime.now(timezone.utc)
    if not dev.get("last_seen"):
        return "never_seen"
    age = now - datetime.fromisoformat(dev["last_seen"])
    return "online" if age <= timedelta(seconds=3 * dev["heartbeat_s"]) else "offline"
