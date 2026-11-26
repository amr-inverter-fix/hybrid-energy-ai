# Test report

Executed 2026-11-27 ~00:34 EET in the build sandbox. Counts are from the actual runs.

| Suite | Command | Result |
|---|---|---|
| Python (supervisor parity, models, reports) | `python3 -m unittest discover -s tests` | 17 tests OK (14 earlier + 3 report-file tests) |
| Backend / API / adapters | `python3 -m pytest -q backend_tests` | 20 passed |
| Node (engine, IoT, maintenance, platform, scenarios) | `node --test tests/test_engine.mjs tests/test_iot_maint.mjs tests/test_platform.mjs tests/test_scenarios.mjs` | 91 pass, 0 fail |
| Browser smoke (headless Chrome, 13 pages, 1280 px and 390 px) | `node tests/e2e_smoke.mjs` with the folder served | 0 JS errors; no horizontal overflow; one favicon 404 |
| Dependency check | `pip-audit -r requirements.txt` | no known vulnerabilities |

## What the new tests cover
- Backend failure cases: missing/wrong key (401), wrong role (403), no keys configured (503), invalid and non-numeric values, NaN, boolean, unknown fields, future/old/naive timestamps, oversized body (413), rate limit (429), duplicate packets, device writing for another device, unregistered device, simulated telemetry never enabling live mode, live needing 10 device packets and an online device, offline detection, WebSocket auth, MQTT topic/payload mismatch and bad JSON, Modbus decode with signed values and missing registers.
- Twin: 8 scenarios each checked for energy balance (residual < 1e-6 Wh), SoC limits, power limits, non-negative unserved energy, served <= requested, traceability fields, determinism, correct effect of each fault.
- Reports: JSON, CSV, XLSX, PDF are re-opened and compared with source numbers; a corrupted CSV and a fake PDF are detected.

## Evaluation runs (not unit tests)
- `forecast_rolling.py`: 5 origins x 5 horizons, simulated data. Mean MAE W (MLP / trailing mean / last value): 1 h 9.2 / 32.0 / 20.3; 3 h 14.0 / 85.2 / 48.4; 6 h 18.9 / 140.7 / 86.3; 12 h 24.3 / 141.2 / 133.2; 24 h 26.3 / 31.3 / 122.3. MLP R2 at 24 h is 0.12. Nominal 80% interval covered 80.0 to 80.9% on average, worst origin 70.9%; daytime coverage is lower than night.
- `eval_cost_reasons.mjs`: timing on Node, not on ESP32.

## Not tested
Real server deployment under uvicorn over a network, a real MQTT broker, a real Modbus device, a real ESP32, TLS, load/concurrency beyond the in-process tests, a real phone, Excel and a PDF viewer opening the generated files (only programmatic re-open), Puter AI button, browser-to-backend calls (not implemented).

## Round 3 (backend connection, language, rule-based sensor checks)
Run on this machine: Python 17 OK; backend 20 passed; node 103 passed (12 new in tests/test_sensor_checks.mjs); browser smoke of all 13 pages, desktop and 390 px, 0 JS errors (favicon 404 only); pip-audit clean (earlier run).
Headless-Chrome check against a local backend (http://localhost, test device named "TEST DEVICE (not real hardware)", 14 posted packets): remote http URL refused; wrong key shows "HTTP 401 (key rejected)"; unreachable host shows an error; correct key shows Connected, live verified yes; live page draws device packets; key is in sessionStorage only, not localStorage; Arabic toggle sets dir=rtl.
Not tested: any hosted backend, cold-start behaviour in the browser (the 70 s timeout is not exercised), the WebSocket from the page, real ESP32 hardware, real fault data for the sensor rules, Arabic text quality review by a native reviewer, screen readers.

## Round 3b (hosted backend, weather provider)
Hosted backend, tested over the internet on 2026-11-27 with a script and with headless Chrome on the real GitHub Pages dashboard: health 200; no key 401; wrong key 401; viewer cannot register (403); admin registered the test device (201); 12 posted packets all 201; live-status live_verified true with 12 valid packets; history 200; CORS header equals https://amr-inverter-fix.github.io; the dashboard connected ("Connected. Devices: 1. Live verified: yes"), drew the live charts, 0 JS errors.
Weather provider: 6 node tests pass (real Open-Meteo fixture, bad inputs rejected, interpolation, twin run with balance residual under 1 Wh, injected-fetch call).
Totals now: node 109 (91 + 12 sensor checks + 6 weather), Python 17, backend 20.
Not tested: WebSocket on the host (not supported there), behaviour after the 3-month expiry, load or concurrency on the free plan, the live Open-Meteo call from the browser, real ESP32 devices, MQTT or Modbus against real brokers/meters.
Deliberately not done: configurable twin time step (the RL policies were trained on 10-minute steps and the engine math is tied to it; changing it would invalidate the reported controller results); battery SoH/RUL (no degradation data).
