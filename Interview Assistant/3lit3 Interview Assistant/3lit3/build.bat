@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ── 3lit3 Interview Assistant — one-command Windows build ────────────────────
rem
rem   build.bat            copy source -> build tree, venv, PyInstaller, patch,
rem                        then Inno Setup if ISCC.exe is available
rem   build.bat --clean    also delete the whole _build tree first
rem
rem Outputs:
rem   shipping\3lit3\_build\dist\3lit3\3lit3.exe        the portable app (onedir)
rem   shipping\3lit3\_build\installer\3lit3_Interview_Assistant.exe   (if Inno found)
rem
rem Secrets/personal data are never bundled: config/api_keys.json, *.env,
rem *.key/*.crt/*.pdf and memory/long_term.json are excluded from the copy, so
rem first run asks the user for their Gemini key and writes it locally.

cd /d "%~dp0"
set "ROOT=%~dp0"
set "SRC=%ROOT%.."
set "BUILD=%ROOT%_build"
set "APP=%BUILD%\app"
set "DIST=%BUILD%\dist\3lit3"
set "INSTALLER_DIR=%BUILD%\installer"

echo.
echo ============================================
echo   3lit3 Interview Assistant - build
echo ============================================
echo.

if /I "%~1"=="--clean" (
    echo [clean] removing _build
    if exist "%BUILD%" rmdir /s /q "%BUILD%"
)

rem ── 0. Preconditions ────────────────────────────────────────────────────────
if not exist "%SRC%\main.py" (
    echo [error] source not found: %SRC%\main.py
    echo         build.bat must live in shipping\3lit3 inside the repo.
    exit /b 1
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [error] python not on PATH. Install Python 3.11+ and re-run.
    exit /b 1
)

if not exist "%BUILD%" mkdir "%BUILD%"

rem ── 1. Copy the source into the build tree (never touch the originals) ──────
echo [1/5] copying source -> %APP%
if exist "%APP%" rmdir /s /q "%APP%"
robocopy "%SRC%" "%APP%" /E /NFL /NDL /NJH /NJS /NP ^
    /XD __pycache__ .venv venv node_modules .git certs logs downloads screenshots 3lit3 tests server ^
    /XF api_keys.json *.key *.crt *.pdf long_term.json .env HANDOFF.md >nul
if errorlevel 8 (
    echo [error] robocopy failed
    exit /b 1
)
if not exist "%APP%\main.py" (
    echo [error] copy did not produce main.py
    exit /b 1
)
echo       done

rem ── 2. Build-time venv + PyInstaller ────────────────────────────────────────
echo [2/5] preparing build venv
if not exist "%BUILD%\venv\Scripts\python.exe" (
    python -m venv "%BUILD%\venv" || (echo [error] venv failed & exit /b 1)
)
set "VPY=%BUILD%\venv\Scripts\python.exe"
"%VPY%" -m pip install --quiet --upgrade pip || (echo [error] pip upgrade failed & exit /b 1)
echo       installing requirements + pyinstaller
"%VPY%" -m pip install --quiet -r "%APP%\requirements.txt" || (echo [error] requirements install failed & exit /b 1)
"%VPY%" -m pip install --quiet pyinstaller || (echo [error] pyinstaller install failed & exit /b 1)

rem ── 3. PyInstaller onedir ───────────────────────────────────────────────────
echo [3/5] PyInstaller onedir (this is the slow step)
rem --distpath/--workpath are pinned: a relative spec path makes PyInstaller fall
rem back to CWD-relative defaults and write dist\ + build\ into the repo root.
"%VPY%" -m PyInstaller --noconfirm --clean ^
    --distpath "%BUILD%\dist" --workpath "%BUILD%\work" "%ROOT%3lit3.spec" || (echo [error] PyInstaller failed & exit /b 1)
if not exist "%DIST%\3lit3.exe" (
    echo [error] expected %DIST%\3lit3.exe not produced
    exit /b 1
)

rem The app resolves read-only assets from the EXE's parent when frozen
rem (get_base_dir() -> Path(sys.executable).parent), but PyInstaller 6 ships data
rem under _internal\. Mirror the two files that are actually READ into the
rem on-disk tree; everything else (config, memory, certs) is created at runtime.
if not exist "%DIST%\core" mkdir "%DIST%\core"
copy /y "%DIST%\_internal\core\prompt.txt"     "%DIST%\core\prompt.txt"     >nul || (echo [error] could not mirror core\prompt.txt & exit /b 1)
copy /y "%DIST%\_internal\core\face_model.obj" "%DIST%\core\face_model.obj" >nul || (echo [error] could not mirror core\face_model.obj & exit /b 1)
echo       built %DIST%\3lit3.exe

rem ── 4. Smoke test — the exe must start and stay alive ───────────────────────
echo [4/5] smoke test (8s launch)
"%VPY%" "%ROOT%smoke_test.py" "%DIST%\3lit3.exe" "%BUILD%\smoke.log"
if errorlevel 1 (
    echo [error] smoke test failed - exe exited during startup. See %BUILD%\smoke.log
    exit /b 1
)

rem ── 5. Installer (Inno Setup) — optional, skipped if not installed ──────────
echo [5/5] installer
set "ISCC="
for %%C in (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
) do if exist %%~C set "ISCC=%%~C"

if not defined ISCC (
    echo       Inno Setup not found - skipping the installer.
    echo       The portable app above is complete and runnable.
    echo       To also build the installer, install Inno Setup 6 and re-run:
    echo           winget install -e --id JRSoftware.InnoSetup
    goto :done
)

if not exist "%INSTALLER_DIR%" mkdir "%INSTALLER_DIR%"
"%ISCC%" /Q "%ROOT%3lit3.iss"
if errorlevel 1 (
    echo [error] ISCC failed
    exit /b 1
)
echo       built %INSTALLER_DIR%\3lit3_Interview_Assistant.exe

:done
echo.
echo ============================================
echo   build complete
echo ============================================
echo   portable app : %DIST%\3lit3.exe
if defined ISCC (
    echo   installer    : %INSTALLER_DIR%\3lit3_Interview_Assistant.exe
) else (
    echo   installer    : skipped ^(Inno Setup not installed^)
)
echo.
exit /b 0
