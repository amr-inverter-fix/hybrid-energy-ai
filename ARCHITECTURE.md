# Architecture (platform release)

Static site (GitHub Pages) + Python research scripts. No backend, no accounts, no secrets.

## Before vs after
| Before | After |
|---|---|
| `index.html`: chat + model demos, numbers only from stored results | `app.html`: 13-section platform (overview, live monitoring, digital twin, forecasting, fault diagnosis, explainable AI, energy management, battery health, IoT devices, assistant, reports, model evaluation, settings). `index.html` is kept and links to it. |
| Simulation in Python only | `twin_engine.js` (physics + energy balance + safety supervisor) is the single engine the UI uses; the UI never recomputes physics. Per-step loss series come from the engine. |
| No tests | 14 Python + 73 node tests, plus a browser smoke test |
| One DQN | DQN, Double DQN, PPO as exchangeable controllers, each optionally wrapped by the supervisor |

## Modules
- `twin_engine.js`: config validation, weather generator, PV/wind/battery/converters, 3 loads classes, KPI + energy balance, `supervise()` (independent of any policy; Python twin in `safety_supervisor.py`, parity vectors in `tests/vectors_supervisor.json`).
- `controllers.js`: hand-written policies come from the engine; neural policies from `v2/rl_weights.json`. Neural nets only propose actions.
- `xai.js`: exact Shapley values for the deployed 7-feature fault MLP (reference = training mean).
- `platform_lib.js`: diagnosis pipeline (validate, observability, classify, explain, inspect), device registry, replay-CSV validation, alarms, battery health, report builders (JSON/CSV/Excel XML), knowledge retrieval with sources.
- `iot_interface.js`, `maintenance.js`: telemetry schema/validator, simulated and HTTP sources; first-generation wear indicators.
- `eval_controllers.mjs`: 5 policies x (raw, +supervisor) x 12 seeds x scenarios (3 seasons, battery 0.5/1/2x, load 0.7/1/1.4x, variability) -> `v2/results_controller_eval.json` (mean, std, 95% CI).
- Python research: `train_*`, `rl_compare.py`, `rl_eval.py`, `export_rl_and_shap.py`, `export_forecast_replay.py`, `report_xlsx.py`.

## Data flow
config (single object, tags given/assumed) -> `Twin.runTwin` -> trace + KPI -> dashboard cards, flow diagram, charts, alarms, health, reports. Reports are built from the same object shown on screen.

## Modes
Simulation (digital twin), Replay (uploaded CSV, every row validated, labelled replay), Live (disabled until a registered device has sent 10 valid `source:"device"` messages with no rejects and is online). Simulated messages are refused by the device registry. Hardware control is not implemented.

## What needs a backend (not built)
Authenticated device endpoints, MQTT broker/bridge, Modbus TCP, persistent history, server-side LLM proxy with credentials, rate limiting. Requirements: HTTPS, per-device tokens stored server-side, input validation (the schema in `iot_interface.js` can be reused), and a reviewed safety design before any control command.

## Install and run
- Site: any static host. Local: `python3 -m http.server 8766` then open `app.html`.
- Tests: `python3 -m unittest discover -s tests`; `node --test tests/test_engine.mjs tests/test_iot_maint.mjs tests/test_platform.mjs`; browser smoke: serve the folder and run `node tests/e2e_smoke.mjs` (needs `puppeteer-core` and Chrome).
- Re-run experiments (Python 3 + tensorflow, scikit-learn, shap, openpyxl): see script headers. `node eval_controllers.mjs` regenerates the controller evaluation.
- Deploy: push to the `main` branch; Pages serves the folder.

## Round 2 additions
- `backend/`: `schema.py` (telemetry fields, units, ranges), `service.py` (single ingest path and live-eligibility rule), `store.py` (SQLite), `security.py` (hashing, rate limit), `app.py` (REST + WebSocket), `adapters.py` (MQTT, Modbus). Endpoints and setup: DEPLOYMENT.md.
- `scenarios.js`: 8 scenarios over `twin_engine.js`; results carry config, assumptions, versions, timestamps.
- `forecast_rolling.py`, `eval_cost_reasons.mjs`, `report_files.py`: evaluation and report tooling with outputs in `v2/`.
- The browser app and the backend are not connected yet (needs a hosted backend).
