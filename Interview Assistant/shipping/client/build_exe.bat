@echo off
REM Single-file build for Interview Assistant client ONLY.
REM Bundles: client/*.py + shared/*.py + license_server.txt (inside exe).
REM Explicitly excludes: ALL .env files, server/, .venv/, build artifacts.
echo Building Interview Assistant into single .exe ...
cd /d "%~dp0"

REM Close any running instance first
taskkill /F /IM InterviewAssistant.exe 2>nul

REM Safety: never ship .env — delete any stale copies in dist/
if exist "dist\.env" del /q "dist\.env"

REM Build — one file, windowed, no console
..\.venv\Scripts\python.exe -m PyInstaller --onefile --windowed --clean --noconfirm --name InterviewAssistant ^
    --distpath dist ^
    --workpath build ^
    --specpath . ^
    --paths "..\shared" ^
    --paths ".." ^
    --add-data "license_server.txt;." ^
    --hidden-import sounddevice ^
    --hidden-import faster_whisper ^
    --hidden-import ctranslate2 ^
    --hidden-import onnxruntime ^
    --hidden-import huggingface_hub ^
    --hidden-import httpx ^
    --hidden-import cryptography ^
    --hidden-import pypdf ^
    --hidden-import docx ^
    --hidden-import numpy ^
    --hidden-import requests ^
    --collect-all faster_whisper ^
    --collect-all ctranslate2 ^
    --collect-all sounddevice ^
    --collect-all onnxruntime ^
    --exclude-module uvicorn ^
    --exclude-module fastapi ^
    --exclude-module psycopg2 ^
    app.py

echo.
echo Copying license_server.txt alongside exe (fallback config, NOT a secret)...
if exist "license_server.txt" copy /y "license_server.txt" "dist\license_server.txt" >nul
echo Verifying NO .env files in dist\ ...
del /q "dist\.env" 2>nul
if exist "dist\server.env" del /q "dist\server.env" 2>nul
dir /b "dist" | findstr /i "\.env" && (
    echo ERROR: .env file found in dist — refusing to ship.
    pause
    exit /b 1
)
echo No .env files in dist. OK.

echo.
echo Done. Exe at: client\dist\InterviewAssistant.exe
echo.
echo To install Desktop shortcut: run install_shortcut.bat
pause
