# Deployment

## 1. Static site (works today)
GitHub Pages serves the repository root: https://amr-inverter-fix.github.io/hybrid-energy-ai/app.html . Push to `main`; Pages rebuilds in about a minute. Local: `python3 -m http.server 8766`, open `http://localhost:8766/app.html`.

## 2. Backend (tested locally only, not hosted)
```
pip install -r requirements.txt
export HYBRID_ADMIN_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
export HYBRID_VIEWER_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
export HYBRID_DB=hybrid.db            # SQLite file
export HYBRID_ORIGINS=https://amr-inverter-fix.github.io   # CORS allow-list (optional)
python3 -m backend.app                # binds 127.0.0.1:8000; set HYBRID_HOST/HYBRID_PORT to change
```
The server refuses to start without `HYBRID_ADMIN_KEY`. Keys live only in the server environment, never in the frontend.

Register a device (returns its API key once; only a hash is stored):
```
curl -X POST localhost:8000/api/v1/devices -H "x-api-key: $HYBRID_ADMIN_KEY" -H 'content-type: application/json' -d '{"device_id":"esp32-01","heartbeat_s":60}'
```
The device then posts JSON to `POST /api/v1/telemetry` with header `x-api-key: <device key>`. Schema: `GET /api/v1/schema` (device_id, timestamp, source, v_batt, i_batt, soc, pv_w, g_wm2, wind_ms, wind_w, load_w, t_batt_c; all sensors optional; timestamp ISO-8601 with timezone). Live mode needs `source:"device"` packets only; simulation and replay packets are stored but never count.
Read: `GET /api/v1/devices`, `/devices/{id}/history`, `/events`, `/live-status`; WebSocket `/ws/telemetry` (header `x-api-key` or `?token=`, viewer or admin key; a token in a URL can appear in logs, prefer the header).

Run the tests: `python3 -m pytest -q backend_tests`.

### MQTT (UNTESTED against a broker)
`backend.adapters.MqttBridge` subscribes to `hybrid/<device_id>/telemetry`. Provide broker host and credentials from environment variables in your own start script; use TLS (`tls=True`). The message handler is unit-tested; the network client is not.

### Modbus TCP (UNTESTED against a device)
`ModbusMap` decodes holding registers (scale, signed). `ModbusPoller` reads them with pymodbus. Decoding is unit-tested; polling is not.

### Hosting
Not hosted. A public host needs an account and HTTPS. Free tiers exist but each is a new account, which needs Amr's approval. Put the backend behind HTTPS, set `HYBRID_ORIGINS`, and replace the in-memory rate limiter with a shared one if you run more than one process.

## 3. Reports
`python3 report_files.py scenario.json outdir` writes and validates report.json/csv/xlsx/pdf (needs openpyxl, reportlab, pdftotext).

## Hosting status (honest)
Deployed: https://amrhybrid.pythonanywhere.com (PythonAnywhere free plan, account `amrhybrid`, registered with Amr's email, no card).
- Why not elsewhere: Render asks for a card even for the free service; Hugging Face Docker Spaces need a paid plan and its signup showed a captcha.
- How it runs: free PythonAnywhere is WSGI only, so `backend/wsgi_shim.py` runs the FastAPI app one request at a time. REST works; WebSocket `/ws/telemetry` does NOT work there. The WSGI file in /var/www holds the admin and viewer keys (file mode 600, never in the repo). Keys are saved in the Instinct vault entries "Hybrid backend admin key (PythonAnywhere)" and "Hybrid backend viewer key (PythonAnywhere)".
- Storage: SQLite at /home/amrhybrid/hybrid.db on PythonAnywhere's persistent disk (unlike Render free).
- Free-plan limits to expect: the web app must be extended from the Web tab about every 3 months or it is disabled; CPU quota per day; outbound internet only to a whitelist (so the backend cannot pull from MQTT brokers or other hosts); one worker.
- Update the code: in a PythonAnywhere Bash console run `cd ~/hybrid-energy-ai && git pull`, then press Reload on the Web tab (or touch the WSGI file).
- A test device named "E2E TEST DEVICE (not real hardware)" with 12 synthetic packets was registered to prove the path. Delete it before using real devices.
