# Acceptance checklist
Done = implemented and covered by a test or smoke run. Partial = works with stated limits. Blocked = needs something not available free/static.

| # | Feature | Status | Notes / blocker |
|---|---|---|---|
| 1 | Overview | Done | KPIs, alarms with acknowledge, source chips on every value |
| 2 | Live Monitoring | Partial | Simulation + CSV replay work. Live disabled until a verified device sends valid data. Blocker: no backend/real device |
| 3 | Digital Twin | Done | Editable config, validation, failure scenarios, energy-balance test |
| 4 | AI Forecasting | Partial | Replay on a simulated season with 80% interval; 24 h worse than baseline; no real weather provider |
| 5 | Fault Diagnosis | Partial | Works; model uncalibrated; unobservable faults flagged rather than detected |
| 6 | Explainable AI | Done | Exact Shapley on the deployed MLP; global KernelSHAP on the same model |
| 7 | Energy Management | Done | 5 policies, supervisor on/off, evaluation with CI. Neural policies out-of-environment |
| 8 | Battery Health | Partial | Indicators only; no SoH/RUL; assumed cycle life |
| 9 | IoT Devices | Partial | Registry, schema validation, rejects simulated data for live. No real transport/auth (needs server) |
| 10 | Engineering Assistant | Partial | Local retrieval with sources works; Puter AI button untested; no manuals/standards loaded |
| 11 | Reports | Partial | JSON/CSV/Excel-XML/print-PDF from the same object; not opened in real Excel |
| 12 | Model Evaluation | Done | Stored metrics and controller eval; simulated-only labelled |
| 13 | Settings | Done | Mode, thresholds, units; no secrets stored |

Not tested: real ESP32, MQTT, Modbus, physical phone, Puter AI, Excel, PDF beyond print CSS. Tests run: 14 Python, 73 node, browser smoke (13 pages, desktop + 390 px).
