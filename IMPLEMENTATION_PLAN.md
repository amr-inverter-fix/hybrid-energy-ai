# Implementation plan (round 2) and what happened

Order followed: reliability (baseline, audit) -> backend/IoT -> twin scenarios -> evaluation upgrades -> reports -> docs. Each step was tested before the next.

1. Audit and baseline: done (UPGRADE_AUDIT.md).
2. Backend: schema + validation, registry, API keys (hashed), roles (admin/viewer/device), rate limit, body limit, SQLite store, WebSocket, MQTT bridge, Modbus map: done, tested in-process (20 tests).
3. Twin scenarios: done (18 tests).
4. Forecast rolling origin, coverage, OOD: done on simulated data.
5. Controller cost and rejection reasons: done.
6. Reports XLSX/PDF validation: done in Python tooling (3 tests).
7. UI: scenario library, rolling-origin table, cost table added to app.html.
8. Not done in this round (see ACCEPTANCE.md): Arabic/English UI, frontend-to-backend connection, hosted backend, weather provider interface code, current-sensor/comms ML classes, SoH/RUL estimator, configurable time step.
