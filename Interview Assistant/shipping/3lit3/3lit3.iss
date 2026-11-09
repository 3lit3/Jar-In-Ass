; ═══════════════════════════════════════════════════════════════════════════
; 3lit3 Interview Assistant — Inno Setup installer (per-user, no admin)
; ═══════════════════════════════════════════════════════════════════════════
;
; Per-user install (PrivilegesRequired=lowest) to {localappdata}\Programs\3lit3
; Interview Assistant. No UAC prompt, no admin rights, no system-wide pollution.
;
; Ships the PyInstaller onedir tree produced by build.bat:
;     _build\dist\3lit3\**   →   {app}\
; including the console-enabled 3lit3.exe. The config directory (Gemini key,
; CV, memory) is created by the app on first run inside {app}\config — it is
; NOT pre-seeded, so no secret ever ships inside the installer.
;
; Registers the myapp:// URL scheme under HKCU (current user only) so links of
; the form myapp://anything launch the assistant. The app currently ignores the
; argument; the scheme exists so callers can deep-link without a hard-coded
; install path.

#define MyAppName "3lit3 Interview Assistant"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "3lit3"
#define MyAppExeName "3lit3.exe"

[Setup]
AppId={{8B5A2F0E-4D6C-4E9A-9C1B-3F7D0A6E5C22}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\3lit3
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=_build\installer
OutputBaseFilename=3lit3_Interview_Assistant
SetupIconFile=..\..\jarvis\config\jarvis.ico
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole onedir tree: exe, _internal\ (libs + bundled data), and the
; on-disk source tree the loaders glob at runtime.
Source: "_build\dist\3lit3\*"; DestDir: "{app}"; \
    Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"; Tasks: desktopicon

; ── myapp:// URL scheme (HKCU — current user only) ──────────────────────────
[Registry]
; URL-scheme handlers register under the BARE scheme name — Software\Classes\myapp,
; not a dotted ProgId. (A ProgId like myapp.3lit3 would not resolve myapp:// links.)
; Uninstall removes the whole key via uninsdeletekey so no dead handler is left.
[Registry]
Root: HKCU; Subkey: "Software\Classes\myapp"; \
    ValueType: string; ValueData: "URL:3lit3 Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\myapp"; \
    ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\myapp\shell\open\command"; \
    ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; Uninstall must not leave the scheme pointing at a deleted exe.
[UninstallDelete]
; First-run config lives under {app}\config — remove it on uninstall so no
; API key or CV is left behind on the machine. (Type: filesandordirs)
Type: filesandordirs; Name: "{app}\config"
Type: filesandordirs; Name: "{app}\memory"
Type: filesandordirs; Name: "{app}\logs"
