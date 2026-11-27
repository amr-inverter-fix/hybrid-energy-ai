# Local AI Architecture

The local AI engine runs entirely on the user's computer. No account, no
subscription, no external AI API, no mandatory internet. The hosted dashboard
(kept at https://amr-inverter-fix.github.io/hybrid-energy-ai/app.html) works
with or without it.

## Components

```
dashboard (browser, GitHub Pages or local file)
   |  HTTP, CORS-restricted, 127.0.0.1 only
   v
local_ai gateway  (FastAPI, python -m local_ai.server, port 8787, binds 127.0.0.1)
   |-- hardware.py        hardware profiler (CPU/RAM/GPU/VRAM/disk/backends)
   |-- model_catalog.py   open-weight model catalog + recommendation by hardware
   |-- rag.py             sqlite document store, BM25 + vector hybrid retrieval
   |-- learning.py        validated data collection, versioned datasets,
   |                      candidate training, evaluation, promotion, rollback
   |-- prompts.py         system prompts (Arabic + English, source-citation rules)
   v
Ollama (local model runtime, 127.0.0.1:11434)
   |-- chat model (default: qwen2.5:3b; hardware-dependent, see MODEL_SELECTION_REPORT.md)
   |-- embedding model (nomic-embed-text; lexical BM25 always available as fallback)
```

## Data flow (chat)

1. Question arrives at `POST /api/local/chat` (with optional live dashboard state).
2. RAG retrieves the most relevant project chunks (BM25 + embeddings merged).
3. The gateway builds a prompt that lists every source and the evidence rules
   (measured / simulation / training-data / calculation / assumption).
4. The local model generates the answer; sources are returned with it.
5. If Ollama or the model is missing, the gateway returns an honest
   retrieval-only answer (`provider: "retrieval-only"`) instead of failing.

## Security boundaries

- The gateway binds 127.0.0.1. It is unreachable from the network.
- CORS allows only the dashboard origin and localhost pages.
- Mutation endpoints (indexing, uploads, records, training, promotion,
  rollback, config) require the local training token in
  `local_ai_data/training_token`, created at first run with owner-only
  permissions. Ordinary dashboard viewing needs no token. This separates
  training permissions from dashboard access.
- The gateway's only outbound connections go to 127.0.0.1:11434 (Ollama).
- Training runs in a background thread with `OMP_NUM_THREADS` capped by config
  (`max_train_threads`, default 2). It never blocks the dashboard or the twin.
- Automatic training never authorizes any control of physical equipment. The
  local AI analyzes and explains; the safety supervisor stays independent.

## Storage (all local, git-ignored `local_ai_data/`)

- `rag.db` — documents, versions, chunks, embeddings.
- `learning.db` — records (accepted/rejected), datasets, models, audit log, config.
- `models/`, `datasets/` — exported model JSON (dashboard-compatible fault
  format: layers/mu/sd/classes) and versioned dataset JSON.
- `config.json`, `training_token`.

## Failure modes by design

- No model installed -> retrieval-only answers, dashboard unaffected.
- Insufficient RAM -> setup recommends a smaller model instead of failing.
- Embedding model missing -> BM25 lexical retrieval keeps working (Arabic and English).
- Training data insufficient -> training is blocked with a clear reason, never faked.
