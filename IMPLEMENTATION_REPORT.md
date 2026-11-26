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
