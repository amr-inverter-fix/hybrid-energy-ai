"""FastAPI backend. Secrets come from environment variables only. See DEPLOYMENT.md."""
import asyncio, json, os, sys
from dataclasses import dataclass
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .schema import FIELDS, SCHEMA_VERSION, SOURCES
from .security import RateLimiter, hash_key, new_key, eq
from .service import Service
from .store import Store, online_status

MAX_BODY = 4096


@dataclass
class Config:
    admin_key: Optional[str] = None
    viewer_key: Optional[str] = None
    db_path: str = ":memory:"
    allowed_origins: tuple = ()
    rate_per_s: float = 5.0
    burst: int = 20


def config_from_env():
    return Config(admin_key=os.environ.get("HYBRID_ADMIN_KEY"), viewer_key=os.environ.get("HYBRID_VIEWER_KEY"),
                  db_path=os.environ.get("HYBRID_DB", "hybrid.db"),
                  allowed_origins=tuple(o for o in os.environ.get("HYBRID_ORIGINS", "").split(",") if o))


def create_app(cfg: Config, clock=None):
    app = FastAPI(title="Hybrid Energy AI backend", version="0.1")
    store = Store(cfg.db_path)
    clients = set()

    async def _bcast(rec):
        dead = []
        for ws in list(clients):
            try:
                await ws.send_text(json.dumps(rec))
            except Exception:
                dead.append(ws)
        for d in dead:
            clients.discard(d)

    loop_ref = {}

    def publish(rec):  # called synchronously from ingest; may run in a worker thread (MQTT)
        lp = loop_ref.get("loop")
        if lp and clients:
            asyncio.run_coroutine_threadsafe(_bcast(rec), lp)

    svc = Service(store, publish)
    limiter = RateLimiter(cfg.rate_per_s, cfg.burst, **({"clock": clock} if clock else {}))
    app.state.service, app.state.store, app.state.cfg = svc, store, cfg
    if cfg.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(cfg.allowed_origins), allow_methods=["GET", "POST"],
                           allow_headers=["x-api-key", "content-type"])

    @app.on_event("startup")
    async def _s():
        loop_ref["loop"] = asyncio.get_running_loop()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        ident = hash_key(request.headers.get("x-api-key", ""))[:16] if request.headers.get("x-api-key") else (request.client.host if request.client else "?")
        if not limiter.allow(ident):
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429, headers={"Retry-After": "1"})
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY:
            return JSONResponse({"detail": "request too large"}, status_code=413)
        if request.method in ("POST", "PUT"):
            body = await request.body()
            if len(body) > MAX_BODY:
                return JSONResponse({"detail": "request too large"}, status_code=413)
        return await call_next(request)

    def role_of(key):
        if not key:
            return None, None
        if cfg.admin_key and eq(key, cfg.admin_key):
            return "admin", None
        if cfg.viewer_key and eq(key, cfg.viewer_key):
            return "viewer", None
        h = hash_key(key)
        for d in store.devices():
            if eq(h, d["key_hash"]):
                return "device", d["device_id"]
        return None, None

    def need(*roles):
        def dep(request: Request):
            if not (cfg.admin_key or cfg.viewer_key):
                raise HTTPException(503, "server has no keys configured; set HYBRID_ADMIN_KEY")
            role, dev = role_of(request.headers.get("x-api-key"))
            if role is None:
                raise HTTPException(401, "missing or invalid API key")
            if role not in roles:
                raise HTTPException(403, f"role '{role}' is not allowed here")
            return role, dev
        return dep

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "schema_version": SCHEMA_VERSION}

    @app.get("/api/v1/schema")
    def schema():
        return {"schema_version": SCHEMA_VERSION, "required": ["device_id", "timestamp", "source"], "sources": list(SOURCES),
                "fields": {k: {"unit": u, "min": lo, "max": hi, "description": d} for k, (u, lo, hi, d) in FIELDS.items()}}

    @app.post("/api/v1/devices", status_code=201)
    async def register(request: Request, auth=Depends(need("admin"))):
        try:
            b = await request.json()
        except Exception:
            raise HTTPException(400, "invalid JSON")
        did = b.get("device_id") if isinstance(b, dict) else None
        from .schema import validate  # reuse id rule
        if not isinstance(did, str) or not (1 <= len(did) <= 64) or not all(c.isalnum() or c in "-_." for c in did):
            raise HTTPException(422, "device_id must be 1-64 chars [A-Za-z0-9._-]")
        hb = b.get("heartbeat_s", 60)
        if not isinstance(hb, int) or isinstance(hb, bool) or not 5 <= hb <= 3600:
            raise HTTPException(422, "heartbeat_s must be an integer 5..3600")
        smap = b.get("sensor_map", {})
        if not isinstance(smap, dict) or any(k not in FIELDS for k in smap):
            raise HTTPException(422, "sensor_map keys must be telemetry field names")
        if store.device(did):
            raise HTTPException(409, "device already registered")
        key = new_key()  # shown once; only its hash is stored
        store.add_device(did, hash_key(key), str(b.get("name", ""))[:80], hb, smap)
        store.event("registered", did, "")
        return {"device_id": did, "api_key": key, "note": "store this key now; it cannot be shown again"}

    def pub_dev(d):
        return {"device_id": d["device_id"], "name": d["name"], "heartbeat_s": d["heartbeat_s"], "last_seen": d["last_seen"],
                "status": online_status(d), "sensor_map": json.loads(d["sensor_map"])}

    @app.get("/api/v1/devices")
    def devices(auth=Depends(need("admin", "viewer"))):
        return [pub_dev(d) for d in store.devices()]

    @app.post("/api/v1/telemetry")
    async def telemetry(request: Request, auth=Depends(need("device"))):
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(400, "invalid JSON")
        out, detail = svc.ingest(payload, authenticated_device=auth[1], via="rest")
        code = {"stored": 201, "duplicate": 200, "rejected": 422, "unknown_device": 404, "forbidden": 403}[out]
        return JSONResponse({"result": out, "detail": detail if out != "stored" else None}, status_code=code)

    @app.get("/api/v1/devices/{device_id}/history")
    def hist(device_id: str, limit: int = 200, source: Optional[str] = None, auth=Depends(need("admin", "viewer"))):
        if source and source not in SOURCES:
            raise HTTPException(422, "bad source")
        if not store.device(device_id):
            raise HTTPException(404, "unknown device")
        return store.history(device_id, max(1, min(limit, 5000)), source)

    @app.get("/api/v1/devices/{device_id}/events")
    def events(device_id: str, auth=Depends(need("admin", "viewer"))):
        if not store.device(device_id):
            raise HTTPException(404, "unknown device")
        return store.events_for(device_id)

    @app.get("/api/v1/devices/{device_id}/live-status")
    def live(device_id: str, auth=Depends(need("admin", "viewer"))):
        return svc.live_status(device_id)

    @app.websocket("/ws/telemetry")
    async def ws(websocket: WebSocket):
        role, _ = role_of(websocket.headers.get("x-api-key") or websocket.query_params.get("token"))
        if role not in ("admin", "viewer"):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)

    return app


def app_from_env():
    """For hosts: uvicorn backend.app:app_from_env --factory"""
    cfg = config_from_env()
    if not cfg.admin_key:
        raise RuntimeError("HYBRID_ADMIN_KEY is not set")
    return create_app(cfg)


def main():  # uvicorn backend.app:app --factory is also fine
    import uvicorn
    cfg = config_from_env()
    if not cfg.admin_key:
        sys.exit("Set HYBRID_ADMIN_KEY (and optionally HYBRID_VIEWER_KEY). Refusing to start without keys.")
    uvicorn.run(create_app(cfg), host=os.environ.get("HYBRID_HOST", "127.0.0.1"), port=int(os.environ.get("HYBRID_PORT", "8000")))


if __name__ == "__main__":
    main()
