@echo off
echo ============================================
echo  Local licensing test (mock payments)
echo  Server: http://127.0.0.1:8000  (mock mode)
echo ============================================
cd /d "%~dp0"

start "IA license server" cmd /k "server\run_server.bat"

echo Waiting for server to come up...
timeout /t 4 /nobreak >nul
:wait
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/status | findstr "200" >nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
echo Server is up. Starting client...
set LICENSE_SERVER_URL=http://127.0.0.1:8000
cd /d "%~dp0client"
..\.venv\Scripts\python.exe app.py %*
pause
