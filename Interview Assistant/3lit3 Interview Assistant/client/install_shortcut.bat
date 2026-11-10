@echo off
REM Creates Desktop + Start Menu shortcuts for Interview Assistant.
REM Works both from shipping/client/ (dev) and from the unzipped folder (end-user).

set "NAME=Interview Assistant"
set "EXE=%~dp0InterviewAssistant.exe"
if not exist "%EXE%" set "EXE=%~dp0dist\InterviewAssistant.exe"
set "WORKDIR=%~dp0"
if exist "%~dp0dist\InterviewAssistant.exe" set "WORKDIR=%~dp0dist"

if not exist "%EXE%" (
    echo ERROR: InterviewAssistant.exe not found next to this script or in dist\.
    echo Run build_exe.bat first.
    pause
    exit /b 1
)

echo EXE: %EXE%

echo Creating Desktop shortcut...
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\%NAME%.lnk'); $s.TargetPath='%EXE%'; $s.WorkingDirectory='%WORKDIR%'; $s.Save()"

echo Creating Start Menu shortcut...
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Programs')+'\%NAME%.lnk'); $s.TargetPath='%EXE%'; $s.WorkingDirectory='%WORKDIR%'; $s.Save()"

echo Shortcuts created on Desktop and Start Menu.
pause
