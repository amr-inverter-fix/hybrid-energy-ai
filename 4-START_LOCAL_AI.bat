@echo off
REM Starts the local AI gateway and opens the dashboard's Local AI page.
REM تشغيل الذكاء الاصطناعي المحلي وفتح اللوحة.
cd /d "%~dp0"
set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
where ollama >nul 2>nul && (start "" /min ollama serve) || (if exist "%OLLAMA_EXE%" start "" /min "%OLLAMA_EXE%" serve)
timeout /t 3 /nobreak >nul
start "" "https://amr-inverter-fix.github.io/hybrid-energy-ai/app.html#localai"
python -m local_ai.server
