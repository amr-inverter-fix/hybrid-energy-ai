#!/usr/bin/env bash
# ============================================================
#  Hybrid Energy AI - ONE-COMMAND LOCAL AI SETUP (macOS / Linux)
#  Run:  bash setup_mac_linux.sh
#  Installs everything needed and downloads the AI model once.
#  After that, no internet, account or subscription is needed.
# ============================================================
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  Hybrid Energy AI - Local AI setup (macOS/Linux)"
echo "============================================================"

# ---- 1. Python ----
if ! command -v python3 >/dev/null 2>&1; then
  echo "[1/4] Python 3 not found. Install it: https://www.python.org/downloads/"
  echo "      (Debian/Ubuntu: sudo apt install python3 python3-pip ; macOS: brew install python3)"
  exit 1
fi
echo "[1/4] Python found: $(python3 --version)"

# ---- 2. Ollama ----
if ! command -v ollama >/dev/null 2>&1; then
  echo "[2/4] Installing Ollama (the local AI runtime)..."
  if [ "$(uname)" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      brew install --cask ollama || brew install ollama
    else
      echo "Install Ollama from https://ollama.com/download then re-run this script."
      exit 1
    fi
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi
else
  echo "[2/4] Ollama found."
fi

# ---- 3. Python packages ----
echo "[3/4] Installing the local AI components..."
python3 -m pip install --user fastapi "uvicorn[standard]" scikit-learn

# ---- 4. Hardware check + model download + verification ----
echo "[4/4] Checking your hardware and downloading the right model..."
python3 -m local_ai.setup_assistant

echo
echo "============================================================"
echo "  SETUP COMPLETE. To use the local AI:"
echo "  ./start_local_ai.sh   then open the dashboard 'Local AI' page."
echo "============================================================"
