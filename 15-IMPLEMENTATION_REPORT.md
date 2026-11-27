# Implementation report (round 2)

New files: backend/{__init__,schema,security,store,service,app,adapters}.py, backend_tests/test_backend.py, scenarios.js, tests/test_scenarios.mjs, tests/test_reports.py, report_files.py, forecast_rolling.py, eval_cost_reasons.mjs, requirements.txt, v2/results_forecast_rolling.json, v2/results_controller_cost.json, UPGRADE_AUDIT.md, IMPLEMENTATION_PLAN.md, IMPLEMENTATION_REPORT.md, TEST_REPORT.md, DEPLOYMENT.md.
Modified: app.html (scenario library, rolling-origin table, controller cost table), ACCEPTANCE.md, ARCHITECTURE.md, README.md.
Existing engine, models, controllers and earlier results were not changed.

Status per feature: see ACCEPTANCE.md. Tests: see TEST_REPORT.md.

## Design decisions
- One validation path (`Service.ingest`) for REST, MQTT and Modbus, so rules cannot drift.
- Live eligibility is decided by the backend (>= 10 valid `source=device` packets and device online), not by the UI.
- Scenarios are layered over the twin without changing its API; sensor failure is modeled as the supervisor receiving an invalid temperature, so the result shows the cost of failing safe.
- Forecast rolling origins use simulator seeds as time order; intervals are split-conformal; the sklearn MLP is a stand-in for the deployed Keras MLP.

## Known limits
Simulated data only; the neural policies come from a different simulator; interval coverage is under nominal in daytime; 24 h forecast is barely better than a trailing mean; no hosted backend; the browser app does not talk to the backend yet; no Arabic UI; no SoH/RUL estimator.

## Round 4 (2026-11-27): local private AI + continuous learning (MASTER PROMPT V2)

- PHASE 1 audit/stabilize: DONE — baseline suites re-run and recorded in TEST_REPORT.md.
- PHASE 2 hardware profiling + local runtime: DONE — `local_ai/hardware.py`,
  `model_catalog.py`, Ollama-based runtime, tiered model recommendation.
  Sandbox-verified; not yet run on Amr's laptop (by design, it runs there).
- PHASE 3 dashboard integration: DONE — new `Local AI` and `Learning Center`
  pages (`local_ai_ui.js`), graceful offline behavior, assistant page points to
  Local AI as the default private provider.
- PHASE 4 local RAG: DONE — sqlite store, heading-aware chunking, hybrid
  BM25 + embedding retrieval, citations, versioning, incremental indexing,
  dedup, subsystem filter, user uploads, Arabic+English.
- PHASE 5 data collection + learning pipeline: DONE — validation, rejection
  with reasons, quality score, sim/device separation, drift detection,
  versioned datasets.
- PHASE 6 versioned candidate training + promotion: DONE — holdout evaluation
  vs production, acceptance criteria, manual promote, rollback, audit log,
  background training with thread cap, auto-train off by default.
- PHASE 7 specialized models: PARTIAL — the fault MLP is now continuously
  trainable with versioning; forecasting and battery SoH/RUL were not changed
  this round (forecasting improvements and any SoH/RUL claim wait for real data).
- PHASE 8 weather into Digital Twin: NOT STARTED this round (provider +
  parsing + tests already existed from round 3; twin UI hookup remains).
- PHASE 9 backend/IoT/hosting: NOT STARTED this round (backend unchanged and
  still passing its 20 tests; PythonAnywhere limits already documented).
- PHASE 10 Arabic/UX: PARTIAL — new pages have Arabic labels and RTL works;
  full localization of every string remains.
- PHASE 11 regression/security/reliability: DONE for this round's scope —
  full suites green, token-gated mutations, CORS-locked localhost gateway.
