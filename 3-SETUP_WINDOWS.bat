@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  Hybrid Energy AI - ONE-COMMAND LOCAL AI SETUP (Windows)
REM  Double-click this file. It installs everything needed and
REM  downloads the AI model once. After that, no internet,
REM  account or subscription is needed.
REM  خطوة واحدة: شغّل الملف وانتظر. بعدها كل شيء يعمل بدون إنترنت.
REM ============================================================
cd /d "%~dp0"

echo.
echo ============================================================
echo   Hybrid Energy AI - Local AI setup (Windows)
echo   اعداد الذكاء الاصطناعي المحلي - خطوة واحدة
echo ============================================================
echo.

REM ---- 1. Python ----
where python >nul 2>nul
if errorlevel 1 (
    echo [1/4] Python not found. Installing Python 3.12 with winget...
    echo       بايثون غير موجود. يتم تثبيته الان...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo.
        echo Could not install Python automatically.
        echo Install it from https://www.python.org/downloads/ ^(check "Add python.exe to PATH"^)
        echo then double-click this file again.
        pause
        exit /b 1
    )
    echo Python installed. Please CLOSE this window and double-click SETUP_WINDOWS.bat again.
    echo تم تثبيت بايثون. اغلق النافذة وشغّل الملف مرة اخرى.
    pause
    exit /b 0
)
echo [1/4] Python found.

REM ---- 2. Ollama (local model runtime) ----
set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
where ollama >nul 2>nul
if errorlevel 1 if not exist "%OLLAMA_EXE%" (
    echo [2/4] Installing Ollama ^(the local AI runtime^)...
    echo       يتم تثبيت مشغّل الذكاء الاصطناعي المحلي...
    winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo Automatic install failed. Downloading the official installer...
        powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '%TEMP%\OllamaSetup.exe'"
        start "" /wait "%TEMP%\OllamaSetup.exe"
    )
) else (
    echo [2/4] Ollama found.
)

REM ---- 3. Python packages for the local gateway ----
echo [3/4] Installing the local AI components (small, free, open source)...
python -m pip install --user --upgrade pip >nul 2>nul
python -m pip install --user fastapi "uvicorn[standard]" scikit-learn
if errorlevel 1 (
    echo pip install failed. Check the messages above, then run this file again.
    pause
    exit /b 1
)

REM ---- 4. Hardware check + model download + verification ----
echo [4/4] Checking your hardware and downloading the right model...
echo       فحص الجهاز وتحميل النموذج المناسب...
python -m local_ai.setup_assistant
if errorlevel 1 (
    echo.
    echo Setup stopped at the step above. Read the message, fix it, and run this file again.
    echo توقف الاعداد عند الخطوة اعلاه. اقرأ الرسالة ثم اعد المحاولة.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   SETUP COMPLETE
echo   To use the local AI: double-click START_LOCAL_AI.bat
echo   then open the dashboard page "Local AI".
echo   اكتمل الاعداد. للتشغيل: START_LOCAL_AI.bat ثم صفحة Local AI
echo ============================================================
pause
