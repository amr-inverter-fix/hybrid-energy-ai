#!/usr/bin/env bash
# Starts the local AI gateway and opens the dashboard's Local AI page.
cd "$(dirname "$0")"
if command -v ollama >/dev/null 2>&1; then
  (ollama serve >/dev/null 2>&1 &)
  sleep 2
fi
( sleep 2; (command -v open >/dev/null 2>&1 && open "https://amr-inverter-fix.github.io/hybrid-energy-ai/app.html#localai") \
  || (command -v xdg-open >/dev/null 2>&1 && xdg-open "https://amr-inverter-fix.github.io/hybrid-energy-ai/app.html#localai") ) >/dev/null 2>&1 &
exec python3 -m local_ai.server
