# Upgrade audit (round 2)

Baseline before any change this round (run 2026-11-27 00:22 EET): `python3 -m unittest discover -s tests` 14 tests OK; `node --test tests/test_engine.mjs tests/test_iot_maint.mjs tests/test_platform.mjs` 73 pass, 0 fail. Browser smoke of 13 pages (desktop + 390 px): 0 JS errors.

## Findings
| # | Finding | Severity | Action this round |
|---|---|---|---|
| 1 | No backend: live mode could only be "unavailable"; no way to receive device data | High | Added `backend/` (FastAPI) with registry, validation, auth, storage, WebSocket, MQTT and Modbus adapters |
| 2 | Scenarios limited to 3 buttons that edit config | Medium | Added `scenarios.js`: 8 named scenarios, traceable results, tests |
| 3 | Forecast metrics came from one fixed split; no empirical interval coverage; no OOD check | Medium | Added `forecast_rolling.py` -> `v2/results_forecast_rolling.json` |
| 4 | No compute cost or rejection reasons for controllers | Low | Added `eval_cost_reasons.mjs` -> `v2/results_controller_cost.json` |
| 5 | Reports in the app were JSON/CSV/Excel-XML/print only and not machine-validated | Medium | Added `report_files.py` (real XLSX with openpyxl, PDF with reportlab) and tests that re-open and compare files |
| 6 | Neural controllers trained on `hybrid_sim.py`, evaluated on the twin | Known limit | Unchanged, documented |
| 7 | The deployed fault model has 5 classes; no current-sensor or communication-fault class | Medium | Not fixed (NOT STARTED). Communication loss is handled at the backend as device offline status, not by the ML model |
| 8 | Time step fixed at 10 min in the twin | Low | Not changed |
| 9 | UI is English with Arabic headings, no full localization | Medium | Not changed |
| 10 | The static app does not call the backend | High | Not changed this round: needs a hosted backend (blocked, see DEPLOYMENT.md) |
| 11 | Duplicate logic: supervisor exists in Python and JS | Low | Kept; parity guarded by `tests/vectors_supervisor.json` |
| 12 | Forecast "persistence" baseline in the new rolling file is the last value, which is weak at long horizons; the trailing mean is the fairer baseline at 24 h | Info | Both reported; see TEST_REPORT |

Dependencies: Python fastapi, uvicorn, httpx, pytest, paho-mqtt, pymodbus (requirements.txt). `pip-audit -r requirements.txt` reported no known vulnerabilities (2026-11-27). The browser app has no npm dependencies.
Secret scan: no keys or tokens in frontend files; `platform_lib.js` rejects credential-like fields in device registrations.
Previous results in `v2/` were not deleted or changed.

## Round 4 audit (2026-11-27)

Scope: MASTER PROMPT V2 (local private AI, RAG, continuous learning).
Repo inspected at commit a55e2f4; all existing components preserved — no
working module was rewritten. New code is additive: `local_ai/` (gateway,
hardware profiler, model catalog, RAG, learning pipeline, prompts, setup
assistant), `local_ai_ui.js` (two dashboard pages), setup/start scripts for
Windows and macOS/Linux, `.gitignore` for `local_ai_data/`, 36 new tests.
Edited: `app.html` (two nav entries + script include + assistant pointer),
`tests/e2e_smoke.mjs` (15 pages; the localhost gateway-offline console error
is the tested degradation path, now filtered with a comment).
Docs added: LOCAL_AI_ARCHITECTURE, MODEL_SELECTION_REPORT, CONTINUOUS_LEARNING,
DATA_GOVERNANCE, LOCAL_AI_SETUP, MODEL_EVALUATION_REPORT.
