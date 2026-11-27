# Model Selection Report

Selection is automatic and hardware-based: `local_ai.hardware` profiles the
machine it runs on, `local_ai.model_catalog.recommend()` picks the largest
model that fits comfortably. Nothing is assumed about a GPU.

## Catalog (open-weight, downloadable once, offline afterwards)

| Tier | Model | Params | Download | Min RAM | License | Arabic |
|---|---|---|---|---|---|---|
| lightweight | qwen2.5:0.5b | 0.5B | ~0.4 GB | 2 GB | Apache 2.0 | basic |
| lightweight | qwen2.5:1.5b | 1.5B | ~1.0 GB | 4 GB | Apache 2.0 | good for size |
| lightweight alt | gemma2:2b | 2B | ~1.6 GB | 6 GB | Gemma Terms of Use | limited |
| recommended | **qwen2.5:3b** | 3B | ~1.9 GB | 6 GB | Qwen Research license* | good |
| recommended alt | llama3.2:3b | 3B | ~2.0 GB | 6 GB | Llama 3.2 Community | limited |
| stronger | qwen2.5:7b | 7B | ~4.7 GB | 12 GB / 6 GB VRAM | Apache 2.0 | very good |
| stronger alt | llama3.1:8b | 8B | ~4.9 GB | 12 GB / 6 GB VRAM | Llama 3.1 Community | limited |

\* The Qwen2.5 3B variant is under the Qwen Research license; the 0.5B/1.5B/7B
variants are Apache 2.0. Each model remains under its own license; see the
URLs in `local_ai/model_catalog.py`. Models are downloaded by Ollama from the
official Ollama registry.

Embedding model: `nomic-embed-text` (~274 MB, Apache 2.0). English-optimized;
Arabic retrieval is backed up by the built-in lexical BM25 index, which needs
no download and always works offline.

## Why Qwen by default

The project is bilingual Arabic/English. Among compact open-weight
instruction models, Qwen2.5 has the strongest Arabic at every size tier, with
competitive English reasoning, and its 0.5B/1.5B/7B sizes are Apache 2.0.

## Decision rules (implemented and unit-tested)

- < 2 GB RAM: no model recommended; dashboard and retrieval still work.
- 2-4 GB: qwen2.5:0.5b.
- 6-11 GB: qwen2.5:3b (default).
- 12+ GB RAM or 6+ GB VRAM: qwen2.5:7b offered as the stronger option.
- Low disk: setup warns with the exact space needed before downloading.
- No GPU: CPU inference (slower, fully offline); noted in the recommendation.

## Verification status (honest)

- Recommendation logic: unit-tested (`tests/test_local_ai.py::TestCatalog`).
- End-to-end install + inference: executed in the Instinct sandbox
  (1 CPU, 1.9 GB RAM, no GPU) with qwen2.5:0.5b and nomic-embed-text:
  download, local inference, Arabic + English prompts, RAG-augmented chat all
  ran. **This was a sandbox, not Amr's laptop.** The 0.5B tier answers
  simple English questions but is weak and repetitive in Arabic; the
  recommended 3B tier is the Arabic default on a normal laptop. CPU/RAM
  benchmarks on Amr's own hardware are produced by
  `python -m local_ai.hardware` during his setup and are NOT in this report,
  because this sandbox is not his machine.
