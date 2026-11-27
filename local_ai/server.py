"""Local AI gateway for the Hybrid Energy AI dashboard.

A small FastAPI server that binds ONLY to 127.0.0.1 (this computer). It is
the single place the dashboard talks to for:
- local LLM chat through the local Ollama runtime (default provider),
- RAG over the project knowledge base,
- the continuous-learning pipeline (records, training, promotion, rollback),
- hardware profile and AI status.

Privacy: no endpoint sends anything off this machine. The only outbound
connections this server ever makes are to 127.0.0.1:11434 (local Ollama).
The dashboard keeps working when this gateway is not running.

Mutation endpoints (records, training, promotion, rollback, config) require
the local training token written by the setup script to
local_ai_data/training_token (this separates training permissions from
ordinary dashboard viewing). Read-only status endpoints need no token
because the server is unreachable from outside this computer anyway.

Run:  python -m local_ai.server            (or START_LOCAL_AI.bat / .sh)
"""
import json
import os
import threading
import time
import urllib.request
import urllib.error

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import __version__
from .hardware import profile as hw_profile
from .model_catalog import recommend, by_id, EMBED_MODEL
from .rag import RagStore, SUBSYSTEM_MAP, RESULT_FILES
from .learning import LearningStore, SOURCES, CLASSES
from .prompts import SYSTEM_EN, SYSTEM_AR_NOTE

REPO_ROOT = os.environ.get("HYBRID_REPO",
                           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.environ.get("HYBRID_LOCAL_AI_DATA", os.path.join(REPO_ROOT, "local_ai_data"))
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
PORT = int(os.environ.get("HYBRID_LOCAL_AI_PORT", "8787"))

os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
TOKEN_PATH = os.path.join(DATA_DIR, "training_token")

DEFAULTS = {
    "chat_model": None,          # set by setup_assistant after profiling
    "embed_model": None,         # set when the embedding model was pulled
    "num_ctx": 4096,
    "temperature": 0.2,
    "max_answer_tokens": 700,
    "chat_timeout_s": 600,
}


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def ensure_token():
    """Create the local training token on first run (never printed to chat)."""
    if not os.path.isfile(TOKEN_PATH):
        import secrets
        with open(TOKEN_PATH, "w") as f:
            f.write(secrets.token_urlsafe(32))
        try:
            os.chmod(TOKEN_PATH, 0o600)
        except OSError:
            pass  # Windows: ACLs are per-user already
    with open(TOKEN_PATH) as f:
        return f.read().strip()


def ollama_get(path, timeout=10):
    with urllib.request.urlopen(OLLAMA + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def ollama_post(path, payload, timeout=600):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(OLLAMA + path, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def ollama_status():
    try:
        j = ollama_get("/api/tags", timeout=5)
        return {"running": True, "models": [m.get("name", "") for m in j.get("models", [])]}
    except Exception as e:
        return {"running": False, "error": type(e).__name__}


class State:
    def __init__(self):
        self.cfg = load_config()
        self.token = ensure_token()
        self.rag = RagStore(os.path.join(DATA_DIR, "rag.db"),
                            embed_url=OLLAMA + "/api/embeddings",
                            embed_model=self.cfg.get("embed_model"))
        self.learn = LearningStore(os.path.join(DATA_DIR, "learning.db"), DATA_DIR)
        self.training = {"active": False, "started_at": None, "result": None}
        self.started_at = time.time()


S = State()
app = FastAPI(title="Hybrid Local AI gateway", version=__version__)
# The dashboard on GitHub Pages and any localhost page may call us; nothing else.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https://amr-inverter-fix\.github\.io$|^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["GET", "POST"],
    allow_headers=["content-type", "x-local-token"],
)

_rate = {}


def rate_limit(req: Request, per_s=5.0):
    key = (req.client.host if req.client else "?", req.url.path)
    now = time.time()
    ts = [t for t in _rate.get(key, []) if now - t < 1.0]
    if len(ts) >= per_s:
        raise HTTPException(429, "rate limit")
    ts.append(now)
    _rate[key] = ts


def need_token(req: Request):
    if req.headers.get("x-local-token", "") != S.token:
        raise HTTPException(403, "local training token required "
                                 "(local_ai_data/training_token on this computer)")


# ---------------- status & hardware ----------------
@app.get("/api/local/status")
def status():
    ol = ollama_status()
    chat_model = S.cfg.get("chat_model")
    model_ready = bool(chat_model and ol.get("running")
                       and any(m.startswith(chat_model.split(":")[0]) for m in ol["models"]))
    return {
        "gateway": "running", "version": __version__, "uptime_s": int(time.time() - S.started_at),
        "ollama": ol, "chat_model": chat_model, "chat_model_ready": model_ready,
        "embed_model": S.cfg.get("embed_model"),
        "num_ctx": S.cfg["num_ctx"],
        "rag": S.rag.stats(), "learning": S.learn.status(),
        "training_active": S.training["active"],
        "privacy": "all processing on this computer; no external AI service is contacted",
    }


@app.get("/api/local/hardware")
def hardware(req: Request):
    rate_limit(req, 1.0)
    p = hw_profile()
    return {"profile": p, "recommendation": recommend(p)}


# ---------------- RAG ----------------
@app.post("/api/local/rag/index")
def rag_index(req: Request):
    rate_limit(req, 0.5)
    need_token(req)
    results = S.rag.index_repo_docs(REPO_ROOT)
    return {"results": results, "stats": S.rag.stats()}


class Upload(BaseModel):
    name: str
    text: str
    subsystem: str = ""


@app.post("/api/local/rag/upload")
def rag_upload(u: Upload, req: Request):
    rate_limit(req)
    need_token(req)
    if len(u.text) > 2_000_000:
        raise HTTPException(413, "document too large (2 MB text limit)")
    if u.name.endswith(".json"):
        kind = "json"
    else:
        kind = "markdown"
    res = S.rag.index_document("uploads/" + u.name, u.text, kind=kind,
                               subsystem=u.subsystem, origin="user upload")
    return res


class Search(BaseModel):
    query: str
    k: int = 5
    subsystem: str = ""


@app.post("/api/local/rag/search")
def rag_search(s: Search, req: Request):
    rate_limit(req)
    return {"hits": S.rag.search(s.query, min(max(s.k, 1), 10), s.subsystem or None)}


# ---------------- chat ----------------
class Chat(BaseModel):
    question: str
    context: dict = {}
    subsystem: str = ""


def build_context(hits, user_ctx):
    parts = []
    for h in hits:
        parts.append("[source: %s > %s (v%s)]\n%s" % (h["source"], h["heading"],
                                                      h["version"], h["text"][:1200]))
    if user_ctx:
        parts.append("[source: live dashboard state (this browser tab)]\n"
                     + json.dumps(user_ctx, ensure_ascii=False)[:2000])
    return "\n\n".join(parts) if parts else "(knowledge base is empty - no project documents indexed yet)"


@app.post("/api/local/chat")
def chat(c: Chat, req: Request):
    rate_limit(req, 2.0)
    q = (c.question or "").strip()
    if not q:
        raise HTTPException(400, "empty question")
    hits = S.rag.search(q, 5, c.subsystem or None)
    ctx = build_context(hits, c.context)
    sources = [{"source": h["source"], "heading": h["heading"], "version": h["version"],
                "score": round(h["score"], 3)} for h in hits]
    ol = ollama_status()
    model = S.cfg.get("chat_model")
    if not (ol["running"] and model):
        return degraded_answer(q, hits, sources,
                               "local model runtime is not running"
                               if not ol["running"] else "no chat model installed yet")
    prompt = SYSTEM_EN.format(context=ctx) + "\n" + SYSTEM_AR_NOTE + "\n\nQUESTION: " + q + "\nANSWER:"
    try:
        r = ollama_post("/api/generate", {
            "model": model, "prompt": prompt, "stream": False,
            "options": {"num_ctx": S.cfg["num_ctx"], "temperature": S.cfg["temperature"],
                        "num_predict": S.cfg["max_answer_tokens"]}},
            timeout=S.cfg["chat_timeout_s"])
        return {"answer": r.get("response", "").strip(), "provider": "local-llm",
                "model": model, "sources": sources,
                "note": "Generated by the local model on this computer from the cited "
                        "project sources. Verify critical numbers against the source pages."}
    except Exception as e:
        return degraded_answer(q, hits, sources, "local inference failed: " + type(e).__name__)


def degraded_answer(q, hits, sources, why):
    """Retrieval-only answer when no LLM is available: honest, still useful."""
    if hits:
        body = ("I could not use the local language model (%s). "
                "Here are the most relevant project sources instead:\n" % why)
        for h in hits:
            body += "\n- %s > %s:\n%s\n" % (h["source"], h["heading"], h["text"][:400])
    else:
        body = ("I could not use the local language model (%s), and the knowledge base "
                "has no matching entries for this question. I cannot answer without "
                "inventing information, so I will not." % why)
    return {"answer": body, "provider": "retrieval-only", "model": None,
            "sources": sources,
            "note": "No AI text generation was used for this answer."}


# ---------------- continuous learning ----------------
class Record(BaseModel):
    ts: float
    origin_id: str
    source: str
    values: dict
    label: str = None
    label_status: str = "suggested"
    model_version: str = None


@app.post("/api/local/learning/records")
def add_record(rec: Record, req: Request):
    rate_limit(req, 100.0)
    need_token(req)
    return S.learn.add_record(rec.model_dump() if hasattr(rec, "model_dump") else rec.dict())


@app.get("/api/local/learning/status")
def learn_status():
    return S.learn.status()


@app.get("/api/local/learning/drift")
def learn_drift(source: str = "device"):
    if source not in SOURCES:
        raise HTTPException(400, "source must be one of " + ",".join(SOURCES))
    return S.learn.drift_report(source)


@app.post("/api/local/learning/train")
def learn_train(req: Request, source: str = "simulation", dataset_id: str = None):
    need_token(req)
    if source not in SOURCES:
        raise HTTPException(400, "source must be one of " + ",".join(SOURCES))
    if S.training["active"]:
        return {"status": "already_running", "started_at": S.training["started_at"]}

    def work():
        S.training.update(active=True, started_at=time.time(), result=None)
        try:
            S.training["result"] = S.learn.train_candidate(source, dataset_id)
        except Exception as e:
            S.training["result"] = {"status": "error", "error": str(e)}
        finally:
            S.training["active"] = False

    threading.Thread(target=work, daemon=True).start()
    return {"status": "started", "note": "training runs in a background thread; "
                                         "poll /api/local/learning/training"}


@app.get("/api/local/learning/training")
def learn_training():
    return S.training


@app.post("/api/local/learning/promote")
def learn_promote(req: Request, model_id: str):
    need_token(req)
    return S.learn.promote(model_id)


@app.post("/api/local/learning/rollback")
def learn_rollback(req: Request):
    need_token(req)
    return S.learn.rollback()


@app.get("/api/local/learning/history")
def learn_history():
    return S.learn.history()


class LearnConfig(BaseModel):
    updates: dict


@app.post("/api/local/learning/config")
def learn_config(c: LearnConfig, req: Request):
    need_token(req)
    return {"updated": S.learn.set_config(c.updates), "config": S.learn.get_config()}


@app.get("/api/local/learning/export_dataset")
def learn_export(source: str = "simulation"):
    """Dataset export is read-only; it returns the file path on THIS computer."""
    ds = S.learn.build_dataset(source)
    return ds


# ---------------- model management ----------------
@app.post("/api/local/config")
def set_gateway_config(c: LearnConfig, req: Request):
    need_token(req)
    allowed = {"chat_model", "embed_model", "num_ctx", "temperature",
               "max_answer_tokens", "chat_timeout_s"}
    for k, v in c.updates.items():
        if k in allowed:
            S.cfg[k] = v
    save_config(S.cfg)
    return {"config": {k: S.cfg[k] for k in allowed}}


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
