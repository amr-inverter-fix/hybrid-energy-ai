"""Local RAG: document store + hybrid retrieval (BM25 + optional embeddings).

Pure stdlib (sqlite3) store. Embedding vectors come from the local Ollama
runtime when its embedding model is installed; when it is not, retrieval
still works through the built-in lexical BM25 index, fully offline.
Nothing here leaves the machine.

Every returned hit carries its source, heading and document version so the
assistant can cite. Chunks are deduplicated by content hash and documents
are versioned: re-indexing a changed file bumps its version and replaces
its chunks; unchanged files are skipped (incremental indexing).
"""
import hashlib
import json
import math
import os
import re
import sqlite3
import time
import urllib.request

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(
  source TEXT, version INTEGER, hash TEXT, added_at REAL, subsystem TEXT,
  title TEXT, origin TEXT, PRIMARY KEY(source, version));
CREATE TABLE IF NOT EXISTS chunks(
  id TEXT PRIMARY KEY, source TEXT, version INTEGER, heading TEXT,
  text TEXT, subsystem TEXT, hash TEXT, embedding TEXT);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(source, version);
"""

TOKEN = re.compile(r"[\w\u0600-\u06FF]{2,}", re.UNICODE)

# Where each known repo document belongs, for context filtering by subsystem.
SUBSYSTEM_MAP = {
    "ARCHITECTURE.md": "platform", "README.md": "platform", "UPGRADE_AUDIT.md": "platform",
    "ACCEPTANCE.md": "platform", "TEST_REPORT.md": "testing", "IMPLEMENTATION_REPORT.md": "platform",
    "DEPLOYMENT.md": "backend", "IOT.md": "iot", "LOCAL_AI_ARCHITECTURE.md": "local-ai",
    "LOCAL_AI_SETUP.md": "local-ai", "CONTINUOUS_LEARNING.md": "learning", "DATA_GOVERNANCE.md": "governance",
    "MODEL_SELECTION_REPORT.md": "local-ai", "MODEL_EVALUATION_REPORT.md": "models",
    "AUDIT.md": "platform", "IMPLEMENTATION_PLAN.md": "platform",
}
RESULT_FILES = {
    "v2/results_fault_v2.json": "fault-diagnosis", "v2/results_fault_explain.json": "fault-diagnosis",
    "v2/results_forecast_v2.json": "forecasting", "v2/results_forecast_rolling.json": "forecasting",
    "v2/results_forecast_seq.json": "forecasting", "v2/results_controller_eval.json": "controllers",
    "v2/results_controller_cost.json": "controllers", "v2/results_rl_compare.json": "controllers",
    "v2/results_rl_ddqn.json": "controllers", "v2/results_rl_ppo.json": "controllers",
    "v2/shap_fault_mlp.json": "explainability", "v2/forecast_replay.json": "forecasting",
    "results_supervised.json": "fault-diagnosis", "results_dispatch_and_extra.json": "controllers",
    "models.json": "models", "data.json": "digital-twin",
}


def _tok(s):
    return TOKEN.findall(s.lower())


def _hash(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def chunk_markdown(source, text, subsystem="", max_len=900, overlap=120):
    """Heading-aware chunking with size cap and overlap. Returns chunk dicts."""
    out, head, buf = [], "(intro)", []

    def flush():
        t = "\n".join(buf).strip()
        while len(t) > max_len:
            out.append({"source": source, "heading": head, "text": t[:max_len], "subsystem": subsystem})
            t = t[max_len - overlap:]
        if len(t) > 40:
            out.append({"source": source, "heading": head, "text": t, "subsystem": subsystem})

    for line in text.split("\n"):
        if re.match(r"^#{1,3} ", line):
            flush()
            head, buf = line.lstrip("# ").strip(), []
        else:
            buf.append(line)
    flush()
    return out


def chunk_json(source, obj, subsystem="", max_len=1200):
    """Flatten a results JSON into a few readable, citable chunks."""
    text = json.dumps(obj, indent=1, ensure_ascii=False)
    chunks, i = [], 0
    while i < len(text):
        chunks.append({"source": source, "heading": "(json)", "text": text[i:i + max_len],
                       "subsystem": subsystem})
        i += max_len
    return chunks


class RagStore:
    def __init__(self, db_path, embed_url="http://127.0.0.1:11434/api/embeddings", embed_model=None):
        self.db_path = db_path
        self.embed_url = embed_url
        self.embed_model = embed_model
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self):
        self.db.close()

    # ---------- embedding (optional; needs the local runtime) ----------
    def embed(self, texts):
        """Return list of vectors, or None if the embedding model is unavailable.
        Uses /api/embed (batch); falls back to legacy /api/embeddings per text."""
        if not self.embed_model:
            return None
        try:
            url = self.embed_url.replace("/api/embeddings", "/api/embed")
            body = json.dumps({"model": self.embed_model, "input": texts}).encode()
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                j = json.loads(r.read().decode())
            embs = j.get("embeddings")
            if embs and len(embs) == len(texts):
                return embs
        except Exception:
            pass
        out = []
        try:
            for t in texts:
                body = json.dumps({"model": self.embed_model, "prompt": t}).encode()
                req = urllib.request.Request(self.embed_url, data=body,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    j = json.loads(r.read().decode())
                out.append(j.get("embedding"))
            if all(out):
                return out
        except Exception:
            pass
        return None

    @staticmethod
    def _cos(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1e-9
        nb = math.sqrt(sum(x * x for x in b)) or 1e-9
        return dot / (na * nb)

    # ---------- indexing ----------
    def index_document(self, source, text, kind="markdown", subsystem="", origin="project repo"):
        """Index one document. Returns {status, version, chunks} (skipped/indexed/duplicate)."""
        subsystem = subsystem or SUBSYSTEM_MAP.get(source) or RESULT_FILES.get(source, "")
        h = _hash(text)
        cur = self.db.execute("SELECT MAX(version), hash FROM documents WHERE source=?",
                              (source,)).fetchone()
        if cur and cur[0] is not None and cur[1] == h:
            return {"status": "skipped", "reason": "unchanged", "source": source, "version": cur[0]}
        version = (cur[0] or 0) + 1 if cur else 1
        chunks = chunk_markdown(source, text, subsystem) if kind == "markdown" \
            else chunk_json(source, json.loads(text), subsystem)
        hashes = [_hash(c["text"]) for c in chunks]
        dupes = sum(1 for ch in hashes if self.db.execute(
            "SELECT 1 FROM chunks WHERE hash=? AND source!=?", (ch, source)).fetchone())
        new_chunks = [c for c, ch in zip(chunks, hashes)]
        embs = self.embed([c["text"] for c in new_chunks]) or [None] * len(new_chunks)
        self.db.execute("DELETE FROM chunks WHERE source=?", (source,))
        for c, ch, em in zip(new_chunks, hashes, embs):
            self.db.execute(
                "INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)",
                (_hash(source + str(version) + ch), source, version, c["heading"],
                 c["text"], c["subsystem"], ch, json.dumps(em) if em else None))
        self.db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                        (source, version, h, time.time(), subsystem,
                         source.split("/")[-1], origin))
        self.db.commit()
        return {"status": "indexed", "source": source, "version": version,
                "chunks": len(new_chunks), "duplicates_detected": dupes}

    def index_repo_docs(self, repo_root, extra_files=None):
        """Index the project's documentation and result files (incremental)."""
        results = []
        files = sorted(set(list(SUBSYSTEM_MAP) + list(RESULT_FILES) + (extra_files or [])))
        for rel in files:
            p = os.path.join(repo_root, rel)
            if not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception:
                continue
            kind = "markdown" if rel.endswith(".md") else "json"
            try:
                results.append(self.index_document(rel, text, kind=kind))
            except Exception as e:
                results.append({"status": "error", "source": rel, "error": str(e)})
        return results

    # ---------- retrieval ----------
    def _bm25(self, query, k, subsystem=None):
        qtok = _tok(query)
        if not qtok:
            return []
        rows = self.db.execute(
            "SELECT id, source, version, heading, text, subsystem FROM chunks").fetchall()
        if subsystem:
            rows = [r for r in rows if r[5] == subsystem]
        if not rows:
            return []
        docs = {r[0]: _tok(r[3] + " " + r[4]) for r in rows}
        df = {}
        for toks in docs.values():
            for w in set(toks):
                df[w] = df.get(w, 0) + 1
        n = len(docs)
        out = []
        for r in rows:
            toks = docs[r[0]]
            tf = {}
            for w in toks:
                tf[w] = tf.get(w, 0) + 1
            s = 0.0
            for w in qtok:
                if w in tf:
                    s += (1 + math.log(tf[w])) * math.log(1 + n / df[w])
            if s > 0:
                out.append({"id": r[0], "source": r[1], "version": r[2], "heading": r[3],
                            "text": r[4], "subsystem": r[5], "bm25": s / math.sqrt(len(toks) + 10)})
        out.sort(key=lambda x: -x["bm25"])
        return out[:k]

    def _vector(self, query, k, subsystem=None):
        qv = self.embed([query])
        if not qv:
            return []
        qv = qv[0]
        rows = self.db.execute(
            "SELECT id, source, version, heading, text, subsystem, embedding FROM chunks "
            "WHERE embedding IS NOT NULL").fetchall()
        if subsystem:
            rows = [r for r in rows if r[5] == subsystem]
        out = []
        for r in rows:
            em = json.loads(r[6])
            out.append({"id": r[0], "source": r[1], "version": r[2], "heading": r[3],
                        "text": r[4], "subsystem": r[5], "vec": self._cos(qv, em)})
        out.sort(key=lambda x: -x["vec"])
        return out[:k]

    def search(self, query, k=5, subsystem=None):
        """Hybrid retrieval: BM25 always; merged with vector scores when embeddings exist."""
        b = self._bm25(query, k * 2, subsystem)
        v = self._vector(query, k * 2, subsystem)
        merged = {}
        for lst, key in ((b, "bm25"), (v, "vec")):
            mx = max([x[key] for x in lst], default=0) or 1
            for x in lst:
                m = merged.setdefault(x["id"], dict(x, bm25=0.0, vec=0.0, vec_available=False))
                m[key] = x[key] / mx
        for m in merged.values():
            m["score"] = m["bm25"] + m["vec"]
            m["vec_available"] = bool(v)
        out = sorted(merged.values(), key=lambda x: -x["score"])[:k]
        for m in out:
            m.pop("embedding", None)
        return out

    def stats(self):
        docs = self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(version),0) FROM documents").fetchone()
        chunks = self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        with_emb = self.db.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0]
        by_sub = dict(self.db.execute(
            "SELECT COALESCE(NULLIF(subsystem,''),'(untagged)'), COUNT(*) FROM chunks "
            "GROUP BY subsystem").fetchall())
        return {"documents": docs[0], "document_versions_total": docs[1], "chunks": chunks,
                "chunks_with_embeddings": with_emb, "by_subsystem": by_sub,
                "embed_model": self.embed_model}
