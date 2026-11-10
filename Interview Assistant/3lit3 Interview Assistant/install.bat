@echo off
REM Installs the 3lit3 assistant: Desktop + Start Menu shortcuts.
REM Double-click this file from the jarvis folder. The shortcut launches
REM python -u main.py with the app folder as the working directory, so the
REM console stays open and the session log is visible while it runs.
REM (Dependencies: run "python setup.py" once if the app has never started.)

setlocal
set "NAME=3lit3"
set "WORKDIR=%~dp0"
set "ICON=%~dp0config\jarvis.ico"

REM Resolve the interpreter to bake into the shortcut: ask python itself
REM for its real executable (the WindowsApps `python` on PATH is an alias
REM stub — a shortcut should target the interpreter, not the redirect).
REM Falls back to where-python; captured at install time, not guessed.
set "PYEXE="
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do if not defined PYEXE set "PYEXE=%%P"
if not defined PYEXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYEXE set "PYEXE=%%P"
if not defined PYEXE (
    echo ERROR: python not found on PATH. Install Python 3.11-3.13 first,
    echo then run "python setup.py" inside this folder before installing.
    pause
    exit /b 1
)
if not exist "%PYEXE%" (
    echo ERROR: resolved python does not exist: %PYEXE%
    pause
    exit /b 1
)

echo Python:  %PYEXE%
echo App:     %WORKDIR%

echo Creating Desktop shortcut...
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; $d=$w.SpecialFolders('Desktop'); $s=$w.CreateShortcut((Join-Path $d '%NAME%.lnk')); $s.TargetPath='%PYEXE%'; $s.Arguments='-u main.py'; $s.WorkingDirectory='%WORKDIR%'; $s.IconLocation='%ICON%'; $s.WindowStyle=1; $s.Save()"

echo Creating Start Menu shortcut...
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; $m=$w.SpecialFolders('Programs'); $s=$w.CreateShortcut((Join-Path $m '%NAME%.lnk')); $s.TargetPath='%PYEXE%'; $s.Arguments='-u main.py'; $s.WorkingDirectory='%WORKDIR%'; $s.IconLocation='%ICON%'; $s.WindowStyle=1; $s.Save()"

if errorlevel 1 (
    echo ERROR: shortcut creation failed.
    pause
    exit /b 1
)

echo.
echo Done - "%NAME%" is on your Desktop and in the Start Menu.
echo Double-click it to launch; the console window shows the live log.
pause
endlocal
