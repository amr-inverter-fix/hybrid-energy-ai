# Model Evaluation Report (local AI round)

This report covers the NEW local-AI components. The pre-existing fault MLP,
forecast and RL controller results are unchanged in `v2/` and TEST_REPORT.md.

## Evaluation harness

`local_ai/learning.py::train_candidate` trains a candidate fault MLP
(scikit-learn, 7 standardized features, 16-16 hidden layers, max 600
iterations) and evaluates it against the current production model on the same
stratified 30% holdout: accuracy, per-class precision/recall/F1, macro F1,
confusion matrix, inference latency per sample. Promotion requires macro F1
gain >= configured minimum and no per-class recall drop beyond the configured
tolerance. All metrics are computed by the pipeline at train time and stored
with the model record (query: Learning Center / `/api/local/learning/history`).

## Sandbox verification (executed 2026-11-27, labelled: NOT Amr's hardware)

Environment: Instinct sandbox, 1 vCPU Xeon Platinum 8375C, 1.9 GB RAM, no GPU,
Linux. Ollama 0.40.18, qwen2.5:0.5b (398 MB) + nomic-embed-text (274 MB).

| Check | Result |
|---|---|
| Ollama install + model download | PASS (one-time download) |
| Local inference (no external calls; runtime at 127.0.0.1) | PASS |
| English chat with RAG sources returned | PASS (plumbing correct; the 0.5B tier misread one number from context — small-model limitation, sources let the user verify) |
| Arabic chat | PASS mechanically; answer quality of the 0.5B tier is poor/repetitive — the 3B recommended tier is the Arabic default |
| RAG index of project docs (26 docs, 580 chunks) | PASS |
| Vector embeddings stored and searchable | PASS (after /api/embed support) |
| BM25 retrieval Arabic + English | PASS (unit tests) |
| Record validation (valid/out-of-range/corrupt/duplicate/unknown-label) | PASS (unit + HTTP) |
| Dataset separation sim vs device | PASS (unit test: two datasets, disjoint sources) |
| Suggested labels excluded from training | PASS (unit test) |
| Train → evaluate → promote → rollback over HTTP | PASS (toy dataset; macro F1 on 30 toy records is plumbing evidence, not a quality claim) |
| Token required on all mutation endpoints | PASS (403 without token) |
| Dashboard with gateway offline (15 pages, mobile + desktop) | PASS: no JS errors; Local AI and Learning Center pages show the offline notice |

## Benchmarks on Amr's laptop

NOT MEASURED — the sandbox is not his machine. His setup script runs
`python -m local_ai.hardware` and verifies a real inference on his hardware;
those numbers belong to his machine and will differ. Honest expectation for a
typical 8 GB RAM CPU-only laptop with qwen2.5:3b: a few tokens per second —
usable for chat, not interactive-real-time.

## What was NOT tested

- Any model other than qwen2.5:0.5b and nomic-embed-text.
- GPU acceleration paths (no GPU in the sandbox).
- Windows execution of the .bat scripts (written for Windows, reviewed, but
  only their Linux-equivalent steps were executed in the sandbox).
- Training on real device telemetry (no physical ESP32 connected yet).
