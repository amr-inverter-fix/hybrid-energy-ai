# Acceptance status (round 2)
DONE = implemented and tested. PARTIAL = works with stated limits. BLOCKED = needs unavailable infrastructure. NOT STARTED = not implemented.

| Feature | Status | Notes |
|---|---|---|
| Overview, alarms, source labels | DONE | smoke-tested, earlier tests |
| Simulation / CSV replay / Verified-live separation (UI + registry) | DONE | simulated packets cannot enable live (JS and backend tests) |
| Backend REST API, device registry, API-key auth, roles | DONE | 20 in-process tests; not run as a hosted server |
| Telemetry schema and validation (units, ranges, timestamps, optional sensors, duplicates) | DONE | tested incl. failure cases |
| Heartbeat / online-offline, event log, rejected packets | DONE | tested |
| Rate limit, request size limit, secrets from env | DONE | in-memory limiter, single process |
| WebSocket real-time | DONE | in-process test |
| MQTT adapter | PARTIAL | handler tested; no broker test |
| Modbus TCP adapter | PARTIAL | decode tested; poller not tested |
| Hosted backend | PARTIAL | live at https://amrhybrid.pythonanywhere.com (free, no card). Tested over the internet: health, role checks (viewer cannot register, wrong key 401), device registration, 12 telemetry posts, live-status verified, history, CORS for the GitHub Pages origin, and the real GitHub Pages dashboard connected and drew the data. Limits: REST only (no WebSocket), 3-monthly manual extension, no real device ever connected |
| Browser app reads data from backend | PARTIAL | Settings connect panel, live page (health, devices, live-status, history), live mode only when backend says live_verified. Tested in headless Chrome against a LOCAL backend with a labelled test device. Not tested against a hosted backend (none deployed). REST polling only; the WebSocket is not used by the page |
| Twin: 8 scenarios with traceable results | DONE | 18 tests, energy balance each |
| Twin: configurable time step | NOT STARTED | fixed 10 min |
| Forecast: horizons 1-24 h, baselines, per-season | DONE | simulated data |
| Forecast: rolling-origin, coverage, OOD | DONE | simulated; day coverage under nominal |
| Forecast: GRU/LSTM in rolling comparison | PARTIAL | GRU/LSTM compared on the fixed split only |
| Weather provider interface | PARTIAL | weather_provider.js: Open-Meteo parser with validation, hourly to 10-min interpolation, feeds runTwin; 6 tests on a REAL Open-Meteo response for Qwesna (fixture). The live network call is only tested with an injected fake fetch; not wired into the app UI; forecast data is not site measurement |
| Fault diagnosis: confusion matrix, P/R/F1, calibration, detection delay, unknown handling | DONE | v2 results, simulated |
| Fault classes for current-sensor and communication faults | PARTIAL | Rule-based checks (not ML classes): stale, gap, timestamp order, stuck/zero/sign-inverted/mismatched battery current. 12 unit tests on synthetic data. Thresholds are assumed. No real fault data, so detection rates are unknown |
| XAI exact Shapley on deployed MLP + global KernelSHAP | DONE | earlier round |
| Battery indicators | PARTIAL | indicators only |
| Battery SoH / RUL estimator | NOT STARTED | no degradation data; deliberately not faked |
| Controller evaluation with CIs, switching, compute cost, rejection reasons | DONE | simulated; timing not ESP32 |
| Safety supervisor independent of AI | DONE | tests, parity vectors |
| Assistant (local retrieval with sources) | PARTIAL | English; Puter AI untested |
| Arabic/English UI localization | PARTIAL | Language toggle, RTL, localized navigation, page titles and subtitles. Page bodies, charts and most labels are still English |
| Reports: JSON/CSV/XLSX/PDF validated | PARTIAL | validated in Python tooling; the browser exports Excel-XML and print-PDF |
| Mobile 390 px | PARTIAL | headless viewport only |
