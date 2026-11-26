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
| Hosted backend | BLOCKED | needs a new (free) account and HTTPS host: Amr's approval |
| Browser app reads data from backend | NOT STARTED | needs hosted backend |
| Twin: 8 scenarios with traceable results | DONE | 18 tests, energy balance each |
| Twin: configurable time step | NOT STARTED | fixed 10 min |
| Forecast: horizons 1-24 h, baselines, per-season | DONE | simulated data |
| Forecast: rolling-origin, coverage, OOD | DONE | simulated; day coverage under nominal |
| Forecast: GRU/LSTM in rolling comparison | PARTIAL | GRU/LSTM compared on the fixed split only |
| Weather provider interface | NOT STARTED | no code, none connected |
| Fault diagnosis: confusion matrix, P/R/F1, calibration, detection delay, unknown handling | DONE | v2 results, simulated |
| Fault classes for current-sensor and communication faults | NOT STARTED | comms loss is device-offline status in backend only |
| XAI exact Shapley on deployed MLP + global KernelSHAP | DONE | earlier round |
| Battery indicators | PARTIAL | indicators only |
| Battery SoH / RUL estimator | NOT STARTED | no degradation data; deliberately not faked |
| Controller evaluation with CIs, switching, compute cost, rejection reasons | DONE | simulated; timing not ESP32 |
| Safety supervisor independent of AI | DONE | tests, parity vectors |
| Assistant (local retrieval with sources) | PARTIAL | English; Puter AI untested |
| Arabic/English UI localization | NOT STARTED | |
| Reports: JSON/CSV/XLSX/PDF validated | PARTIAL | validated in Python tooling; the browser exports Excel-XML and print-PDF |
| Mobile 390 px | PARTIAL | headless viewport only |
