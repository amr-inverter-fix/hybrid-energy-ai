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
